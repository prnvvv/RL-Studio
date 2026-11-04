"""Interim versus final verification: the incident policy, against real still-training runs.

Real: Studio training (a run that is genuinely active while it is verified), the deterministic engine, persistence and
Person 4 incident registration. Mocked: only the hosted-model transport. Verification needs no model at all.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.studio.manager import manager
from backend.studio.tests.test_studio import BASE
from backend.verification.tests.phase3_support import (
    TRAINING,
    ExplodingAI,
    ScriptedProvider,
    make_ai,
    reward_proposal,
    statements_json,
)

P = "/api/v1/projects"
V = "/api/v1/verification"
LOW = "the final episode reward must be at least 100000"
HIGH = "the final episode reward must be at least 200000"
EASY = "the final episode reward must be at least 1"
LONG = {**TRAINING, "total_timesteps": 400000, "eval_every": 200000, "checkpoint_every": 200000}


def h(pid: str) -> dict[str, str]:
    return {"X-Project-ID": pid}


def incidents(client: TestClient, run_id: str) -> list[dict[str, Any]]:
    with client.app.state.database.read() as db:  # type: ignore[attr-defined]
        return [dict(r) for r in db.execute("SELECT * FROM incidents WHERE run_id = ?", (run_id,))]


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    root: Path = tmp_path_factory.mktemp("interim")
    mp = pytest.MonkeyPatch()
    mp.setenv("STUDIO_DATA_DIR", str(root / "studio"))
    mp.setenv("RL_STUDIO_DATA_ROOT", str(root / "var"))
    with TestClient(create_app()) as c:
        yield c
        for session in list(manager._sessions.values()):
            with contextlib.suppress(Exception):
                session.stop()
            thread = getattr(session, "_thread", None)
            if thread is not None:
                thread.join(timeout=15)
        manager._sessions.clear()
    mp.undo()


def new_project(client: TestClient, name: str, *statements: tuple[str, float]) -> tuple[str, dict[str, str]]:
    pid = client.post(P, json={"name": name}).json()["project_id"]
    provider = ScriptedProvider(statements_json(*(t for t, _ in statements)),
                                [reward_proposal(t, value=v) for t, v in statements])
    client.app.state.ai_service = make_ai(provider)  # type: ignore[attr-defined]
    text = "; ".join(t for t, _ in statements)
    reqs = client.post(f"{P}/{pid}/intents", json={"statement": text}).json()["intents"][0]["requirements"]
    ids = {r["source_statement"]: r["requirement_id"] for r in reqs}
    for rid in ids.values():
        assert client.post(f"{P}/{pid}/requirements/{rid}/confirm").status_code == 200
    client.app.state.ai_service = ExplodingAI()  # type: ignore[attr-defined]
    return pid, ids


def start_active_run(client: TestClient, pid: str) -> tuple[str, str]:
    sid = client.post(f"{BASE}/sessions", json={"agent": "PPO", "environment": "cartpole", "training": LONG},
                      headers=h(pid)).json()["session_id"]
    assert client.post(f"{BASE}/sessions/{sid}/start", headers=h(pid)).status_code == 200
    run_id = client.get(f"{BASE}/sessions/{sid}", headers=h(pid)).json()["run_id"]
    return sid, run_id


def verify_when_evidence(client: TestClient, pid: str, run_id: str, **body: Any) -> dict[str, Any]:
    deadline = time.time() + 90
    while time.time() < deadline:
        r = client.post(f"{P}/{pid}/verifications", json={"run_id": run_id, **body})
        if r.status_code == 201:
            return r.json()
        assert r.status_code == 202, r.text
        time.sleep(0.3)
    raise AssertionError("no episode completed in time")


def wait_for_episode(client: TestClient, pid: str, run_id: str) -> None:
    deadline = time.time() + 90
    while time.time() < deadline:
        if client.get(f"{BASE}/runs/{run_id}/episodes", headers=h(pid)).json().get("items", client.get(f"{BASE}/runs/{run_id}/episodes", headers=h(pid)).json().get("episodes", [])):
            return
        time.sleep(0.3)
    raise AssertionError("no episode completed in time")


def stop_and_wait(client: TestClient, pid: str, sid: str) -> None:
    client.post(f"{BASE}/sessions/{sid}/stop", headers=h(pid))
    deadline = time.time() + 60
    while time.time() < deadline:
        if client.get(f"{BASE}/sessions/{sid}", headers=h(pid)).json().get("status") in {"stopped", "completed", "failed"}:
            return
        time.sleep(0.2)
    raise AssertionError("session did not stop")


STATE: dict[str, Any] = {}


def test_interim_failure_is_persisted_but_deferred_not_an_incident(client: TestClient) -> None:
    pid, ids = new_project(client, "Interim", (LOW, 100000), (EASY, 1))
    sid, run_id = start_active_run(client, pid)
    STATE.update(pid=pid, ids=ids, sid=sid, run=run_id)

    out = verify_when_evidence(client, pid, run_id)
    ver = out["verification"]
    assert out["interim"] is True and out["finality"] == "interim" and ver["finality"] == "interim"
    statuses = {x["source_statement"]: x["status"] for x in ver["results"]}
    # FAIL and UNKNOWN are persisted as results. A still-training run can never PASS: Phase 3 withholds PASS until
    # the run is complete, so the satisfiable requirement is UNKNOWN, not a provisional pass.
    assert statuses == {LOW: "fail", EASY: "unknown"}
    assert ver["overall_status"] == "fail"
    assert ver["incident"]["handoff_status"] == "deferred_interim" and ver["incident"]["incident_id"] is None
    assert incidents(client, run_id) == []  # no ordinary incident from a provisional failure
    rows = client.get(f"{P}/{pid}/verifications", params={"run_id": run_id}).json()["verifications"]
    assert {r["evaluation_status"] for r in rows} == {"fail", "unknown"} and {r["stage"] for r in rows} == {"during_training"}
    STATE["interim_ver"] = ver["verification_id"]


def test_retries_are_idempotent_and_never_create_an_incident(client: TestClient) -> None:
    pid, run_id, vid = STATE["pid"], STATE["run"], STATE["interim_ver"]
    for _ in range(3):
        retry = client.post(f"{V}/verifications/{vid}/incident/retry", headers=h(pid))
        assert retry.status_code == 200
        assert retry.json()["incident"]["handoff_status"] == "deferred_interim"
    replay = client.post(f"{P}/{pid}/verifications", json={"run_id": run_id, "idempotency_key": "x"}).json()
    again = client.post(f"{P}/{pid}/verifications", json={"run_id": run_id, "idempotency_key": "x"}).json()
    assert replay["verification"]["verification_id"] == again["verification"]["verification_id"]
    assert incidents(client, run_id) == []


def test_promotion_creates_exactly_one_incident_and_is_idempotent(client: TestClient) -> None:
    pid, run_id, vid = STATE["pid"], STATE["run"], STATE["interim_ver"]
    first = client.post(f"{P}/{pid}/verifications/{vid}/promote")
    assert first.status_code == 200, first.text
    link = first.json()["incident"]
    assert link["handoff_status"] == "created_interim" and link["incident_id"]
    for _ in range(2):
        again = client.post(f"{P}/{pid}/verifications/{vid}/promote").json()["incident"]
        assert again["incident_id"] == link["incident_id"]
    stored = incidents(client, run_id)
    assert len(stored) == 1 and stored[0]["incident_id"] == link["incident_id"]
    STATE["incident"] = link["incident_id"]


def test_final_verification_reuses_the_promoted_incident_instead_of_duplicating(client: TestClient) -> None:
    pid, run_id, sid = STATE["pid"], STATE["run"], STATE["sid"]
    stop_and_wait(client, pid, sid)
    final = client.post(f"{P}/{pid}/verifications", json={"run_id": run_id}).json()
    assert final["interim"] is False and final["finality"] == "final" and final["stage"] == "post_training"
    ver = final["verification"]
    assert ver["finality"] == "final" and ver["verification_id"] != STATE["interim_ver"]
    assert ver["incident"]["handoff_status"] == "created"  # the existing final-FAIL handoff, unchanged...
    assert ver["incident"]["incident_id"] == STATE["incident"]  # ...but it joined the promoted incident
    assert len(incidents(client, run_id)) == 1


def test_a_final_failure_still_registers_an_incident_as_before(client: TestClient) -> None:
    pid, _ids = new_project(client, "FinalOnly", (LOW, 100000))
    sid, run_id = start_active_run(client, pid)
    wait_for_episode(client, pid, run_id)
    stop_and_wait(client, pid, sid)
    final = client.post(f"{P}/{pid}/verifications", json={"run_id": run_id}).json()
    ver = final["verification"]
    assert final["finality"] == "final" and ver["overall_status"] == "fail"
    assert ver["incident"]["handoff_status"] == "created" and ver["incident"]["incident_id"]
    assert len(incidents(client, run_id)) == 1


def test_only_an_explicitly_critical_requirement_raises_an_immediate_incident(client: TestClient) -> None:
    pid, ids = new_project(client, "Critical", (LOW, 100000), (HIGH, 200000))
    # nothing is critical unless the user says so
    assert all(r["critical_safety"] is False for r in client.get(f"{P}/{pid}/requirements").json()["requirements"])
    flagged = client.put(f"{P}/{pid}/requirements/{ids[LOW]}/critical", json={"critical": True})
    assert flagged.status_code == 200 and flagged.json()["critical_safety"] is True

    sid, run_id = start_active_run(client, pid)
    out = verify_when_evidence(client, pid, run_id)
    ver = out["verification"]
    assert out["interim"] is True and {x["status"] for x in ver["results"]} == {"fail"}
    assert ver["incident"]["handoff_status"] == "created_interim" and ver["incident"]["incident_id"]
    stored = incidents(client, run_id)
    assert len(stored) == 1
    import json as _json

    details = _json.loads(stored[0]["details_json"])
    assert details["critical_safety"] is True and details["provisional"] is True and details["finality"] == "interim"
    # only the critical requirement is in the incident; the other interim failure stays provisional
    assert len(details["failed_requirement_ids"]) == 1

    retry = client.post(f"{V}/verifications/{ver['verification_id']}/incident/retry", headers=h(pid)).json()
    assert retry["incident"]["incident_id"] == ver["incident"]["incident_id"] and len(incidents(client, run_id)) == 1

    stop_and_wait(client, pid, sid)
    final = client.post(f"{P}/{pid}/verifications", json={"run_id": run_id}).json()["verification"]
    # The final verification fails both requirements. The critical one already has an incident (not duplicated);
    # only the remaining failure is registered, as one new incident.
    assert final["incident"]["handoff_status"] == "created"
    assert final["incident"]["incident_id"] != ver["incident"]["incident_id"]
    assert len(final["incident"]["failed_requirement_ids"]) == 1  # this incident covers the remainder only
    after = incidents(client, run_id)
    assert len(after) == 2
    by_id = {i["incident_id"]: _json.loads(i["details_json"]) for i in after}
    assert len(by_id[final["incident"]["incident_id"]]["failed_requirement_ids"]) == 1
    covered = {r for d in by_id.values() for r in d["failed_requirement_ids"]}
    assert len(covered) == 2  # every failure is in exactly one incident

    cleared = client.put(f"{P}/{pid}/requirements/{ids[LOW]}/critical", json={"critical": False}).json()
    assert cleared["critical_safety"] is False


def test_interim_unknown_creates_no_incident(client: TestClient) -> None:
    pid, _ids = new_project(client, "PassOnly", (EASY, 1))
    sid, run_id = start_active_run(client, pid)
    out = verify_when_evidence(client, pid, run_id)
    ver = out["verification"]
    assert ver["overall_status"] != "pass"  # never a provisional PASS while the run is active
    assert ver["overall_status"] != "fail" and ver["incident"]["handoff_status"] == "not_required"
    assert incidents(client, run_id) == []
    assert client.post(f"{P}/{pid}/verifications/{ver['verification_id']}/promote").status_code == 409
    stop_and_wait(client, pid, sid)


def test_policy_guards(client: TestClient) -> None:
    pid, run_id, vid = STATE["pid"], STATE["run"], STATE["interim_ver"]
    # only confirmed requirements can be flagged
    provider = ScriptedProvider(statements_json(LOW), [reward_proposal(LOW, value=100000)])
    client.app.state.ai_service = make_ai(provider)  # type: ignore[attr-defined]
    draft = client.post(f"{P}/{pid}/intents", json={"statement": f"{LOW} again"}).json()["intents"][0]["requirements"][0]
    assert client.put(f"{P}/{pid}/requirements/{draft['requirement_id']}/critical", json={"critical": True}).status_code == 409
    # a final verification cannot be "promoted": it hands off by itself
    final_vid = next(v["verification_id"] for v in client.get(f"{P}/{pid}/verifications", params={"run_id": run_id}).json()["verifications"]
                     if v["stage"] == "post_training")
    assert client.post(f"{P}/{pid}/verifications/{final_vid}/promote").status_code == 409
    # another project cannot promote this project's verification
    other = client.post(P, json={"name": "Other"}).json()["project_id"]
    assert client.post(f"{P}/{other}/verifications/{vid}/promote").status_code == 404
