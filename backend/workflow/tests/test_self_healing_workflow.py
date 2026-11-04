"""The whole self-healing workflow through the real HTTP API, on one isolated data root.

Real:   project defaults, a real Stable-Baselines3 CartPole training run, its persisted metrics and checkpoints,
        real policy rollouts for evaluation, requirement validation, the deterministic verification engine, the
        Person 4 incident / recovery / evaluation records, SQLite persistence, project isolation.
Mocked: ONLY the hosted-model HTTP transport (``httpx.MockTransport``). The Meta replies are scripted, so these
        tests prove the wiring and safety rules, not that a live Meta call works or that any account can use a model.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.studio.manager import manager
from backend.studio.tests.test_studio import BASE
from backend.verification.tests.phase3_support import (
    SECRET,
    TRAINING,
    ScriptedProvider,
    make_ai,
    responses_ok,
)

P = "/api/v1/projects"
V = "/api/v1"
STATE: dict[str, Any] = {}


def h(pid: str | None) -> dict[str, str]:
    return {} if pid is None else {"X-Project-ID": pid}


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    root = tmp_path_factory.mktemp("selfheal")
    mp = pytest.MonkeyPatch()
    mp.setenv("STUDIO_DATA_DIR", str(root / "studio"))
    mp.setenv("RL_STUDIO_DATA_ROOT", str(root / "var"))
    with TestClient(create_app()) as c:
        yield c
        for session in list(manager._sessions.values()):
            try:
                session.stop()
            except Exception:  # noqa: BLE001
                pass
    manager._sessions.clear()
    mp.undo()


def _wait(client: TestClient, pid: str, sid: str) -> dict[str, Any]:
    deadline = time.time() + 90
    snap: dict[str, Any] = {}
    while time.time() < deadline:
        snap = client.get(f"{BASE}/sessions/{sid}", headers=h(pid)).json()
        if snap.get("status") in {"completed", "failed", "stopped"}:
            return snap
        time.sleep(0.1)
    raise AssertionError(f"training never finished: {snap}")


class Meta:
    """Scripted Meta transport for the assistant and the advisory diagnosis; records every request."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.root_cause: dict[str, Any] = {}
        self.recovery: dict[str, Any] = {}
        self.chat_reply = "PPO clips the policy ratio so updates stay small."

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append(body)
        system = body["input"][0]["content"]
        if "RL Studio assistant" in system:
            text = self.chat_reply
        elif "recommend recovery options" in system:
            text = json.dumps(self.recovery)
        else:
            text = json.dumps(self.root_cause)
        return httpx.Response(200, json=responses_ok(text, body["model"], f"resp_{len(self.calls)}"))


def test_1_project_defaults_are_persisted_and_restored(client: TestClient) -> None:
    created = client.post(
        P, json={"name": "Self-healing", "agent": {"agent": "PPO"}, "environment": {"environment": "cartpole"}}
    ).json()
    pid = created["project_id"]
    STATE["pid"] = pid
    reopened = client.get(f"{P}/{pid}").json()  # a reopen / refresh reads the same record
    assert reopened["agent"] == {"agent": "PPO"} and reopened["environment"] == {"environment": "cartpole"}
    client.patch(f"{P}/{pid}", json={"agent": {"agent": "A2C"}})  # an explicit change replaces the default
    assert client.get(f"{P}/{pid}").json()["agent"] == {"agent": "A2C"}
    client.patch(f"{P}/{pid}", json={"agent": {"agent": "PPO"}})


def test_2_real_training_run_is_persisted_for_the_project(client: TestClient) -> None:
    pid = STATE["pid"]
    r = client.post(
        f"{BASE}/sessions",
        json={"agent": "PPO", "environment": "cartpole", "training": TRAINING, "project_id": pid},
        headers=h(pid),
    )
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    assert client.post(f"{BASE}/sessions/{sid}/start", headers=h(pid)).status_code == 200
    snap = _wait(client, pid, sid)
    assert snap["status"] == "completed", snap.get("error")
    STATE["run"] = snap["run_id"]
    detail = client.get(f"{P}/{pid}/training-runs/{snap['run_id']}").json()
    assert detail["run"]["project_id"] == pid and len(detail["checkpoints"]) >= 1


def test_3_the_saved_policy_is_evaluated_without_retraining_and_history_is_append_only(client: TestClient) -> None:
    pid, run = STATE["pid"], STATE["run"]
    first = client.post(f"{V}/runs/{run}/evaluations", json={"episodes": 4}, headers=h(pid))
    assert first.status_code == 201, first.text
    ev = first.json()
    assert ev["status"] == "completed" and ev["run_id"] == run and ev["project_id"] == pid
    assert ev["episode_count"] == 4 and len(ev["seeds"]) == 4 and ev["environment_version"] == "CartPole-v1"
    assert ev["policy_fingerprint"] and len(ev["policy_fingerprint"]) == 64 and ev["artifact_id"].startswith("ckpt_")
    assert ev["algorithm"] == "PPO" and ev["metrics"]["summary"]["valid_episode_count"] == 4
    assert ev["metrics"]["variability"]["reward_std"] is not None and ev["baseline"] is None
    assert [e["seed"] for e in ev["episodes"]] == ev["seeds"]  # the exact seeds were played
    second = client.post(
        f"{V}/runs/{run}/evaluations",
        json={"episodes": 4, "baseline_evaluation_id": ev["run_evaluation_id"]},
        headers=h(pid),
    ).json()
    assert second["run_evaluation_id"] != ev["run_evaluation_id"]  # a repeat adds a row, never overwrites
    assert second["baseline"]["comparable"] and second["baseline"]["paired"]
    assert second["baseline"]["identity"]["run_evaluation_id"] == ev["run_evaluation_id"]
    assert second["metrics"]["summary"]["mean_reward"] == ev["metrics"]["summary"]["mean_reward"]  # deterministic
    listed = client.get(f"{V}/runs/{run}/evaluations", headers=h(pid)).json()
    assert listed["count"] == 2 and listed["evaluations"][0]["run_evaluation_id"] == second["run_evaluation_id"]
    missing = client.post(
        f"{V}/runs/{run}/evaluations", json={"episodes": 2, "baseline_evaluation_id": "reval_missing"}, headers=h(pid)
    )
    assert missing.status_code == 404  # a baseline is never fabricated
    STATE["evaluation"] = ev["run_evaluation_id"]


def test_4_evaluation_is_isolated_between_projects(client: TestClient) -> None:
    other = client.post(P, json={"name": "Other"}).json()["project_id"]
    run = STATE["run"]
    assert client.get(f"{V}/runs/{run}/evaluations", headers=h(other)).status_code == 404
    assert client.post(f"{V}/runs/{run}/evaluations", json={"episodes": 1}, headers=h(other)).status_code == 404
    assert client.get(f"{V}/runs/{run}/evaluations/{STATE['evaluation']}", headers=h(other)).status_code == 404


def test_5_general_assistant_answers_with_no_incident_and_uses_persisted_context(client: TestClient) -> None:
    pid, run = STATE["pid"], STATE["run"]
    meta = Meta()
    client.app.state.ai_service = make_ai(meta)  # type: ignore[attr-defined]
    bare = client.post(f"{V}/assistant/chat", json={"message": "What does PPO clip range do?"})
    assert bare.status_code == 200, bare.text  # no project, no run, no incident: still answered
    assert bare.json()["reply"] == meta.chat_reply and bare.json()["mode"] == "general"
    assert any("no project is selected" in m for m in bare.json()["context"]["not_available"])
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    scoped = client.post(
        f"{V}/assistant/chat", json={"message": "How did my run do?", "run_id": run, "history": history}, headers=h(pid)
    )
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["context"]["run_id"] == run and scoped.json()["context"]["incident_id"] is None
    sent = meta.calls[-1]["input"]
    prefix = "platform_context: "
    ctx = json.loads(next(m["content"] for m in sent if m["content"].startswith(prefix))[len(prefix):])
    assert ctx["run"]["run_id"] == run and ctx["run"]["algorithm"] == "PPO" and ctx["project"]["project_id"] == pid
    assert ctx["evaluations"] and ctx["evaluations"][0]["summary"]["valid_episode_count"] == 4
    assert [m["role"] for m in sent][-3:] == ["user", "assistant", "user"]  # the conversation is carried
    assert SECRET not in json.dumps(meta.calls) + scoped.text  # the key never reaches the model or the client
    other = client.post(P, json={"name": "Isolated"}).json()["project_id"]
    assert client.post(f"{V}/assistant/chat", json={"message": "x", "run_id": run}, headers=h(other)).status_code == 404


def test_6_assistant_reports_an_unavailable_provider_instead_of_inventing_an_answer(client: TestClient) -> None:
    keep = client.app.state.ai_service  # type: ignore[attr-defined]
    down = ScriptedProvider()
    down.mode = "down"
    client.app.state.ai_service = make_ai(down)  # type: ignore[attr-defined]
    try:
        r = client.post(f"{V}/assistant/chat", json={"message": "hello"})
    finally:
        client.app.state.ai_service = keep  # type: ignore[attr-defined]
    assert r.status_code == 503 and r.json()["error"]["code"] == "AI-005" and "upstream detail" not in r.text
    assert client.post(f"{V}/assistant/chat", json={"message": "   "}).status_code in (400, 422)


STRICT = "the final episode reward must be at least 100000"


def test_7_a_strict_confirmed_requirement_fails_deterministically_and_opens_one_incident(client: TestClient) -> None:
    from backend.verification.tests.phase3_support import reward_proposal, statements_json

    pid, run = STATE["pid"], STATE["run"]
    provider = ScriptedProvider(statements_json(STRICT), [reward_proposal(STRICT, value=100000)])
    client.app.state.ai_service = make_ai(provider)  # type: ignore[attr-defined]
    body = client.post(f"{P}/{pid}/intents", json={"statement": STRICT}).json()
    req = body["intents"][0]["requirements"][0]
    assert req["lifecycle_status"] in {"draft", "needs_clarification"} or req.get("status")
    assert client.post(f"{P}/{pid}/requirements/{req['requirement_id']}/confirm").status_code == 200
    ver = client.post(f"{P}/{pid}/verifications", json={"run_id": run}).json()["verification"]
    assert ver["overall_status"] == "fail"  # decided by the deterministic engine, not by any model
    assert ver["incident"]["handoff_status"] == "created"
    STATE["incident"], STATE["verification"] = ver["incident"]["incident_id"], ver["verification_id"]
    again = client.post(f"{P}/{pid}/verifications", json={"run_id": run}).json()["verification"]
    assert again["verification_id"] == ver["verification_id"]  # no duplicate verification or incident
    detail = client.get(f"{P}/{pid}/training-runs/{run}").json()
    assert [i["incident_id"] for i in detail["incidents"]] == [STATE["incident"]]
    # the Diagnosis & Recovery page reads the incident from persisted records only
    inc = STATE["incident"]
    record = client.get(f"{V}/incidents/{inc}", headers=h(pid)).json()
    assert record["run_id"] == run and record["verification_id"] == ver["verification_id"]
    assert record["detection_status"] == "confirmed" and record["diagnosis_status"] == "unresolved"
    assert record["requirement"]["source_statement"] == STRICT and record["requirement"]["expected_value"] == 100000
    shown = client.get(f"{V}/incidents/{inc}/verification", headers=h(pid)).json()
    assert shown["overall_status"] == "fail" and shown["results"][0]["status"] == "fail"
    assert client.get(f"{V}/incidents/{inc}/evidence", headers=h(pid)).json()
    assert client.get(f"{V}/incidents/{inc}/anomalies", headers=h(pid)).json() == []  # nothing is invented
    listed = client.get(f"{V}/incidents", params={"run_id": run}, headers=h(pid)).json()
    assert [i["incident_id"] for i in listed["incidents"]] == [inc]
    assert client.get(f"{V}/incidents/{inc}", headers=h(client.post(P, json={"name": "Peeker"}).json()["project_id"])).status_code == 404


def test_8_incident_diagnosis_is_grounded_and_recovery_options_never_execute(client: TestClient) -> None:
    pid, run, inc = STATE["pid"], STATE["run"], STATE["incident"]
    meta = Meta()
    meta.root_cause = {
        "summary": "The requirement threshold is far above what a 2000-step run reaches.",
        "observed_facts": [{"statement": "The requirement failed deterministically.",
                            "evidence_ids": [f"incident:{inc}"]}],
        "hypotheses": [{"component": "configuration", "description": "The stated threshold is unattainable.",
                        "supporting_evidence_ids": [f"incident:{inc}", "invented:ref"], "confidence": 0.9,
                        "uncertainty": "no longer training run to compare"}],
        "missing_evidence": [], "recommended_investigation": ["train longer"], "limitations": [],
    }
    client.app.state.ai_service = make_ai(meta)  # type: ignore[attr-defined]
    r = client.post(f"{V}/incidents/{inc}/investigations", headers=h(pid))
    assert r.status_code == 201, r.text
    record = r.json()
    assert record["kind"] == "root_cause"
    hyp = record["result"]["hypotheses"][0]
    assert record["result"]["confirmed"] is False and hyp["kind"] == "inference"  # a model never confirms a cause
    assert "invented:ref" not in hyp["supporting_evidence_ids"]  # a reference that does not exist is removed
    assert hyp["confidence"] < 0.9  # confidence is capped deterministically
    # the incident-scoped assistant answers about THIS incident, from its evidence, and cites only real references
    meta.chat_reply = f"The evidence index lists incident:{inc}."
    chat = client.post(f"{V}/assistant/chat", json={"message": "Why did this fail?", "incident_id": inc}, headers=h(pid))
    assert chat.status_code == 200, chat.text
    assert chat.json()["mode"] == "incident" and chat.json()["context"]["incident_id"] == inc
    assert chat.json()["task"] == "investigation_assistance"
    other = client.post(P, json={"name": "Elsewhere"}).json()["project_id"]
    assert client.post(f"{V}/assistant/chat", json={"message": "x", "incident_id": inc}, headers=h(other)).status_code == 404


def test_9_recovery_is_recommended_then_executed_only_with_authorization_and_is_validated_by_rollout(client: TestClient) -> None:
    pid, run, inc = STATE["pid"], STATE["run"], STATE["incident"]
    arts = client.get(f"{V}/runs/{run}/artifacts", headers=h(pid)).json()
    items = arts["artifacts"] if isinstance(arts, dict) else arts
    checkpoints = [a for a in items if a["artifact_type"] == "checkpoint"]
    target = checkpoints[0]
    meta = Meta()
    meta.recovery = {
        "summary": "Evaluate the saved policy again from a recorded checkpoint.",
        "options": [{"action": "restore_checkpoint", "reason": "known-good policy", "target_checkpoint_id": target["checkpoint_id"],
                     "supporting_evidence_ids": [f"incident:{inc}"], "requires_user_authorization": False}],
    }
    client.app.state.ai_service = make_ai(meta)  # type: ignore[attr-defined]
    rec = client.post(f"{V}/incidents/{inc}/recovery-recommendations", headers=h(pid))
    assert rec.status_code == 201, rec.text
    option = rec.json()["result"]["options"][0]
    assert option["requires_user_authorization"] is True  # the model cannot waive authorization
    assert client.get(f"{V}/incidents/{inc}/recoveries/none", headers=h(pid)).status_code == 404

    # A verification failure records no corruption interval, so no checkpoint can be proven unexposed: the fail-closed
    # recovery policy refuses it, and nothing is executed. Authorization cannot override an ineligible assessment.
    refused = client.post(f"{V}/incidents/{inc}/recoveries", json={
        "recovery_strategy": "restore_checkpoint", "source_checkpoint_id": target["artifact_id"], "execute": True,
        "approval": {"approved": True, "approved_by": "tester"}}, headers=h(pid))
    assert refused.status_code == 201 and refused.json()["recovery_status"] == "blocked"
    assert refused.json()["executed_actions"] == [] or all(a["status"] != "completed" for a in refused.json()["executed_actions"])
    assert refused.json()["recovery_artifact_id"] is None
    STATE["target"] = target


def test_10_an_authorized_restore_executes_and_the_recovered_policy_is_validated_by_rollout(client: TestClient) -> None:
    """A recoverable incident needs a recorded corruption interval. Verification failures carry none, so this
    incident is SEEDED through the Person 4 registration contract (it is test data, not a verification result):
    it declares everything after the first checkpoint as affected."""
    from backend.provenance.models import IncidentRegistration

    pid, run = STATE["pid"], STATE["run"]
    arts = client.get(f"{V}/runs/{run}/artifacts", headers=h(pid)).json()
    items = arts["artifacts"] if isinstance(arts, dict) else arts
    checkpoints = sorted((a for a in items if a["artifact_type"] == "checkpoint"), key=lambda a: a["timestep"])
    assert len(checkpoints) >= 2
    source, first_affected = checkpoints[0], checkpoints[1]
    client.app.state.services.provenance.register_incident(IncidentRegistration(  # type: ignore[attr-defined]
        incident_id="inc_seeded_recoverable", run_id=run, environment_id="cartpole", environment_version="CartPole-v1",
        source_environment_version="CartPole-v1", corruption_start_timestep=source["timestep"] + 1,
        corruption_end_timestep=first_affected["timestep"] + 10_000, severity="high",
        summary="SEEDED TEST INCIDENT with a declared corruption interval", evidence_ids=[f"checkpoint:{first_affected['checkpoint_id']}"]))
    inc = "inc_seeded_recoverable"
    assessment = client.post(f"{V}/incidents/{inc}/recovery-assessments", json={
        "recovery_strategy": "restore_checkpoint", "source_checkpoint_id": source["artifact_id"]}, headers=h(pid))
    assert assessment.status_code == 201, assessment.text
    a = assessment.json()
    assert a["recovery_eligibility"] in {"eligible", "needs_review"}, a["compatibility"]
    outcomes = {c["name"]: c["outcome"] for c in a["compatibility"]}
    # the Studio checkpoint now records real facts about its own archive, so these are no longer "unknown"
    assert outcomes["serialization_compatibility"] == "pass" and outcomes["space_compatibility"] == "pass"
    assert outcomes["state_components"] == "pass" and outcomes["exposure_classification"] == "pass"

    unapproved = client.post(f"{V}/incidents/{inc}/recoveries", json={
        "assessment_id": a["recovery_assessment_id"], "execute": True}, headers=h(pid)).json()
    assert unapproved["recovery_status"] == "blocked" and unapproved["recovery_artifact_id"] is None  # no authorization, no action

    done = client.post(f"{V}/incidents/{inc}/recoveries", json={
        "assessment_id": a["recovery_assessment_id"], "execute": True,
        "approval": {"approved": True, "approved_by": "tester", "note": "reviewed advisory options"}}, headers=h(pid)).json()
    assert done["recovery_status"] == "completed" and done["recovery_artifact_id"], (done["failure_reason"], done["errors"], done["executed_actions"])
    assert any(x["action"] == "restore_checkpoint" and x["status"] == "completed" for x in done["executed_actions"])

    # completed is not verified: only the evaluation of the policy this recovery produced can say so
    assert client.get(f"{V}/incidents/{inc}/recoveries/{done['recovery_id']}", headers=h(pid)).json()["recovery_status"] == "completed"
    evaluated = client.post(f"{V}/incidents/{inc}/recoveries/{done['recovery_id']}/evaluate", json={"episodes": 3}, headers=h(pid))
    assert evaluated.status_code == 201, evaluated.text
    body = evaluated.json()
    assert body["recovered_policy"]["artifact_id"] == done["recovery_artifact_id"]  # the recovered artifact, not the source
    assert body["evaluation"]["recovery_verified"] is False  # no acceptance criteria were configured: never a free pass
    assert body["evaluation"]["evaluation_status"] == "inconclusive"
    assert body["evaluation"]["episode_count"] == 3 and len(body["evaluation"]["seeds"]) == 3
    strict = client.post(f"{V}/incidents/{inc}/recoveries/{done['recovery_id']}/evaluate", json={
        "episodes": 3, "acceptance_criteria": {"minimum_recovered_success_rate": 0.0}}, headers=h(pid)).json()
    assert strict["evaluation"]["evaluation_status"] == "passed" and strict["evaluation"]["recovery_verified"] is True
    listed = client.get(f"{V}/incidents/{inc}/evaluations", headers=h(pid)).json()
    purposes = {e.get("purpose") for e in listed["evaluations"] if "purpose" in e}
    assert {"post_recovery", "recovery_baseline"} <= purposes  # the rollouts themselves are persisted
    reports = client.get(f"{P}/{pid}/training-runs/{run}").json()
    assert reports["run"]["run_id"] == run
