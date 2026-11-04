"""Real end-to-end project lifecycle: pre-, during- and post-training intent through ONE Phase 3 pipeline.

Real:   Studio training runs (small CartPole PPO) through the HTTP API, the Phase 2 evidence builder, requirement
        validation, the LangGraph workflows, the deterministic verification engine, SQLite persistence and the
        Person 4 incident registration.
Mocked: only the hosted-model HTTP transport (``ScriptedProvider``). No live Groq / Hugging Face call is made, and
        nothing here claims one.
No run id, episode, metric or verification result is hand-built.
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
from backend.studio.tests.test_studio import BASE, _wait
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
OK = "the final episode reward must be at least 1"
IMPOSSIBLE = "the final episode reward must be at least 100000"


def _start(client: TestClient, project_id: str | None, training: dict[str, Any] | None = None) -> str:
    body: dict[str, Any] = {"agent": "PPO", "environment": "cartpole", "training": training or TRAINING}
    if project_id:
        body["project_id"] = project_id
    response = client.post(f"{BASE}/sessions", json=body)
    assert response.status_code == 201, response.text
    sid = response.json()["session_id"]
    assert client.post(f"{BASE}/sessions/{sid}/start").status_code == 200
    return sid


def _train(client: TestClient, project_id: str | None) -> str:
    sid = _start(client, project_id)
    snap = _wait(client, sid, {"completed", "failed"})
    assert snap["status"] == "completed", snap.get("error")
    return snap["run_id"]


def _script(client: TestClient, *proposals: tuple[str, float]) -> ScriptedProvider:
    provider = ScriptedProvider(statements_json(*(t for t, _ in proposals)),
                                [reward_proposal(t, value=v) for t, v in proposals])
    client.app.state.ai_service = make_ai(provider)  # type: ignore[attr-defined]
    return provider


@pytest.fixture(scope="module")
def roots(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    root = tmp_path_factory.mktemp("projlife")
    mp = pytest.MonkeyPatch()
    mp.setenv("STUDIO_DATA_DIR", str(root / "studio"))
    mp.setenv("RL_STUDIO_DATA_ROOT", str(root / "var"))
    yield root
    mp.undo()


@pytest.fixture(scope="module")
def client(roots: Path) -> Iterator[TestClient]:
    with TestClient(create_app()) as c:
        yield c
        for session in list(manager._sessions.values()):
            with contextlib.suppress(Exception):
                session.stop()
            thread = getattr(session, "_thread", None)
            if thread is not None:
                thread.join(timeout=15)
        manager._sessions.clear()


STATE: dict[str, Any] = {}


def test_1_pre_training_requirements_are_saved_and_confirmed_with_no_run(client: TestClient) -> None:
    project = client.post(P, json={"name": "Lifecycle", "agent": {"agent": "PPO"}, "environment": {"environment": "cartpole"}}).json()
    pid = project["project_id"]
    STATE["pid"] = pid
    _script(client, (OK, 1), (IMPOSSIBLE, 100000))
    body = client.post(f"{P}/{pid}/intents", json={"statement": f"Quality bar: {OK}; also {IMPOSSIBLE}."}).json()
    assert body["stage"] == "pre_training"
    reqs = {r["source_statement"]: r for r in body["intents"][0]["requirements"]}
    assert set(reqs) == {OK, IMPOSSIBLE}
    for r in reqs.values():
        assert client.post(f"{P}/{pid}/requirements/{r['requirement_id']}/confirm").status_code == 200
    STATE["ok_req"], STATE["bad_req"] = reqs[OK]["requirement_id"], reqs[IMPOSSIBLE]["requirement_id"]
    # nothing about a run exists yet
    assert client.get(f"{P}/{pid}/runs").json()["runs"] == []
    assert client.get(f"{P}/{pid}").json()["training"]["state"] == "not_started"
    assert client.get(f"{P}/{pid}/verifications").json()["verifications"] == []


def test_2_training_started_later_belongs_to_the_project_and_sees_saved_requirements(client: TestClient) -> None:
    pid = STATE["pid"]
    run_id = _train(client, pid)
    STATE["run1"] = run_id
    runs = client.get(f"{P}/{pid}/runs").json()["runs"]
    assert [r["run_id"] for r in runs] == [run_id] and runs[0]["status"] == "completed" and runs[0]["episode_count"]
    detail = client.get(f"{P}/{pid}").json()
    assert detail["training"] == {"state": "completed", "run_count": 1, "active_runs": 0, "completed_runs": 1}
    assert detail["requirements"]["confirmed"] == 2
    # the run registration carries the project; the training config was not altered
    run = client.get(f"/api/v1/studio/runs/{run_id}").json()
    assert "project_id" not in run["config"]
    with client.app.state.database.read() as conn:  # type: ignore[attr-defined]
        assert conn.execute("SELECT project_id FROM runs WHERE run_id = ?", (run_id,)).fetchone()[0] == pid


def test_3_post_training_verification_uses_the_original_engine_and_actual_evidence(client: TestClient) -> None:
    pid, run_id = STATE["pid"], STATE["run1"]
    client.app.state.ai_service = ExplodingAI()  # type: ignore[attr-defined]  # any model call would fail the test
    r = client.post(f"{P}/{pid}/verifications", json={"run_id": run_id, "idempotency_key": "post-1"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "evaluated" and body["stage"] == "post_training" and body["interim"] is False
    ver = body["verification"]
    assert ver["run_id"] == run_id and ver["overall_status"] == "fail"  # a mandatory failure is never an overall pass
    statuses = {x["source_statement"]: x["status"] for x in ver["results"]}
    assert statuses == {OK: "pass", IMPOSSIBLE: "fail"}
    assert ver["traceability"]["run_id"] == run_id and ver["traceability"]["event_ids"] and ver["traceability"]["episode_ids"]
    # the existing Person 3 -> Person 4 handoff happened for the failure
    assert ver["incident"]["handoff_status"] == "created" and ver["incident"]["incident_id"]
    # the run-scoped record is the original lifecycle's own verification
    direct = client.get(f"{V}/verifications/{ver['verification_id']}").json()
    assert direct["overall_status"] == "fail" and direct["run_id"] == run_id

    rows = client.get(f"{P}/{pid}/verifications", params={"run_id": run_id}).json()["verifications"]
    assert {(x["requirement_id"], x["evaluation_status"]) for x in rows} == {(STATE["ok_req"], "pass"), (STATE["bad_req"], "fail")}
    assert all(x["evidence_references"] and x["evaluation_window"]["episodes"] >= 1 and x["requirement_revision"] == 1 for x in rows)
    STATE["ver1"] = ver["verification_id"]

    replay = client.post(f"{P}/{pid}/verifications", json={"run_id": run_id, "idempotency_key": "post-1"}).json()
    assert replay["verification"]["verification_id"] == ver["verification_id"]
    assert len(client.get(f"{P}/{pid}/verifications").json()["verifications"]) == 2  # no duplicate rows
    listed = {r["requirement_id"]: r for r in client.get(f"{P}/{pid}/requirements").json()["requirements"]}
    assert listed[STATE["bad_req"]]["latest_verification"]["status"] == "fail"
    assert client.get(f"{P}/{pid}").json()["last_verification"]["status"] in {"pass", "fail"}


def test_4_new_requirement_after_training_gets_a_new_verification_and_history_is_immutable(client: TestClient) -> None:
    pid, run_id = STATE["pid"], STATE["run1"]
    before = client.get(f"{V}/verifications/{STATE['ver1']}/results").json()["results"]
    extra = "the final episode reward must be at least 2"
    _script(client, (extra, 2))
    req = client.post(f"{P}/{pid}/intents", json={"statement": f"Another bar: {extra}", "run_id": run_id}).json()
    assert req["stage"] == "post_training" and req["run_id"] == run_id
    rid = req["intents"][0]["requirements"][0]["requirement_id"]
    client.post(f"{P}/{pid}/requirements/{rid}/confirm")
    client.app.state.ai_service = ExplodingAI()  # type: ignore[attr-defined]
    second = client.post(f"{P}/{pid}/verifications", json={"run_id": run_id, "requirement_ids": [rid]}).json()
    assert second["verification"]["verification_id"] != STATE["ver1"]
    assert [x["status"] for x in second["verification"]["results"]] == ["pass"]
    after = client.get(f"{V}/verifications/{STATE['ver1']}/results").json()["results"]
    assert after == before  # the earlier result was not rewritten
    assert len(client.get(f"{P}/{pid}/verifications", params={"run_id": run_id}).json()["verifications"]) == 3


def test_5_revising_a_requirement_creates_a_new_revision_and_keeps_the_old_result(client: TestClient) -> None:
    pid, run_id = STATE["pid"], STATE["run1"]
    revised_text = "the final episode reward must be at least 3"
    _script(client, (revised_text, 3))
    revised = client.post(f"{P}/{pid}/intents", json={"statement": revised_text, "supersedes": STATE["ok_req"]}).json()
    new = revised["intents"][0]["requirements"][0]
    assert new["requirement_revision"] == 2 and new["supersedes"] == STATE["ok_req"]
    assert new["requirement_key"] == STATE["ok_req"]
    client.post(f"{P}/{pid}/requirements/{new['requirement_id']}/confirm")
    listed = {r["requirement_id"]: r for r in client.get(f"{P}/{pid}/requirements").json()["requirements"]}
    assert listed[STATE["ok_req"]]["superseded"] is True and listed[new["requirement_id"]]["superseded"] is False
    client.app.state.ai_service = ExplodingAI()  # type: ignore[attr-defined]
    default = client.post(f"{P}/{pid}/verifications", json={"run_id": run_id}).json()
    verified_ids = {x["requirement_id"] for x in client.get(f"{P}/{pid}/verifications", params={"run_id": run_id}).json()["verifications"]
                    if x["verification_id"] == default["verification"]["verification_id"]}
    assert STATE["ok_req"] not in verified_ids and new["requirement_id"] in verified_ids  # only the current revision runs
    old_rows = [x for x in client.get(f"{P}/{pid}/verifications").json()["verifications"] if x["requirement_id"] == STATE["ok_req"]]
    assert old_rows and old_rows[0]["evaluation_status"] == "pass"  # history of revision 1 untouched
    # a revision must be exactly one requirement; an ambiguous one is refused and its proposals are withdrawn
    four, five = "the final episode reward must be at least 4", "the final episode reward must be at least 5"
    _script(client, (four, 4), (five, 5))
    bad = client.post(f"{P}/{pid}/intents", json={"statement": f"{four} and {five}", "supersedes": new["requirement_id"]})
    assert bad.status_code == 422 and bad.json()["detail"]["error"]["details"] == {"proposed": 2}
    withdrawn = [r for r in client.get(f"{P}/{pid}/requirements").json()["requirements"] if r["source_statement"] in (four, five)]
    assert len(withdrawn) == 2 and {r["lifecycle_status"] for r in withdrawn} == {"rejected"}


def test_6_isolation_and_legacy_runs(client: TestClient) -> None:
    pid, run_id = STATE["pid"], STATE["run1"]
    other = client.post(P, json={"name": "Other"}).json()["project_id"]
    assert client.get(f"{P}/{other}/runs").json()["runs"] == []
    assert client.post(f"{P}/{other}/verifications", json={"run_id": run_id}).status_code == 404
    assert client.get(f"{P}/{other}/verifications", params={"run_id": run_id}).status_code == 404
    assert client.get(f"{P}/{other}/requirements").json()["requirements"] == []
    assert client.get(f"{P}/{other}/verifications").json()["verifications"] == []
    # a run created outside any project is legacy: it is not silently assigned to anyone
    legacy_run = _train(client, None)
    assert legacy_run in [r["run_id"] for r in client.get(f"{P}/legacy-runs").json()["runs"]]
    assert legacy_run not in [r["run_id"] for r in client.get(f"{P}/{pid}/runs").json()["runs"]]
    assert client.post(f"{P}/{pid}/verifications", json={"run_id": legacy_run}).status_code == 404
    assert client.post(f"{P}/{other}/runs/{run_id}/adopt").status_code == 409  # already owned: never reassigned
    adopted = client.post(f"{P}/{other}/runs/{legacy_run}/adopt")
    assert adopted.status_code == 200
    assert [r["run_id"] for r in client.get(f"{P}/{other}/runs").json()["runs"]] == [legacy_run]
    assert legacy_run not in [r["run_id"] for r in client.get(f"{P}/legacy-runs").json()["runs"]]


def test_7_during_training_waits_for_evidence_then_evaluates_without_touching_training(client: TestClient) -> None:
    pid = STATE["pid"]
    client.app.state.ai_service = ExplodingAI()  # type: ignore[attr-defined]
    training = {**TRAINING, "total_timesteps": 400000, "eval_every": 200000, "checkpoint_every": 200000}
    sid = _start(client, pid, training)
    run_id = client.get(f"{BASE}/sessions/{sid}").json()["run_id"]
    assert run_id and client.get(f"{P}/{pid}/runs").json()["runs"][0]["run_id"] == run_id

    waited, evaluated = False, None
    deadline = time.time() + 90
    while time.time() < deadline and evaluated is None:
        r = client.post(f"{P}/{pid}/verifications", json={"run_id": run_id, "requirement_ids": [STATE["bad_req"]]})
        if r.status_code == 202:
            waited = True
            assert r.json()["state"] == "waiting_for_evidence" and r.json()["verification"] is None
            time.sleep(0.3)
        else:
            assert r.status_code == 201, r.text
            evaluated = r.json()
    assert evaluated is not None, "no episode completed in time"
    snap = client.get(f"{BASE}/sessions/{sid}").json()
    assert evaluated["stage"] == "during_training" and evaluated["interim"] is True
    assert snap["status"] in {"running", "completed"}  # verification did not stop or fail the run
    assert evaluated["evaluation_window"]["episodes"] >= 1 and evaluated["evaluation_window"]["run_status"] == "running"
    rows = [x for x in client.get(f"{P}/{pid}/verifications", params={"run_id": run_id}).json()["verifications"]]
    assert rows and rows[0]["stage"] == "during_training"
    del waited  # an immediate 202 is timing dependent, so it is not asserted

    # new expectations can be submitted while training is active; the stage is recorded
    text = "the final episode reward must be at least 7"
    _script(client, (text, 7))
    during = client.post(f"{P}/{pid}/intents", json={"statement": text, "run_id": run_id}).json()
    assert during["stage"] == "during_training" and during["requirement_count"] == 1
    assert client.get(f"{BASE}/sessions/{sid}").json()["status"] in {"running", "completed"}

    client.post(f"{BASE}/sessions/{sid}/stop")
    _wait(client, sid, {"stopped", "completed", "failed"}, timeout=60)
    assert client.get(f"{BASE}/sessions/{sid}").json()["status"] in {"stopped", "completed"}


def test_8_everything_is_read_back_after_a_restart(client: TestClient, roots: Path) -> None:
    pid, run_id = STATE["pid"], STATE["run1"]
    with TestClient(create_app()) as fresh:
        assert fresh.get(f"{P}/{pid}").json()["name"] == "Lifecycle"
        reqs = fresh.get(f"{P}/{pid}/requirements").json()["requirements"]
        assert STATE["ok_req"] in {r["requirement_id"] for r in reqs}
        rows = fresh.get(f"{P}/{pid}/verifications", params={"run_id": run_id}).json()["verifications"]
        assert {x["verification_id"] for x in rows} >= {STATE["ver1"]}
        assert fresh.get(f"{V}/verifications/{STATE['ver1']}").json()["overall_status"] == "fail"
        assert len(fresh.get(f"{P}/{pid}/runs").json()["runs"]) >= 2
