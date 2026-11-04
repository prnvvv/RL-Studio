"""Phase 3 real-pipeline integration test and HTTP contract tests.

What is real here
    * a small Studio training run executed through the real Studio HTTP API and training pipeline
    * isolated SQLite databases (Studio store + provenance/verification database)
    * the Phase 2 evidence builder, requirement validation, LangGraph workflows, the deterministic
      verification engine, persistence and the Person 4 ``ProvenanceService`` incident registration
What is NOT real
    * the hosted model: only the Meta HTTP transport is scripted. This test makes no live Meta
      call and does not verify live provider behaviour.
No ``VerificationInput``, event or evidence record is hand-built.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.studio.session import store_path
from backend.studio.store import TrajectoryReader
from backend.verification.input.studio_evidence import build_studio_evidence
from backend.verification.tests.phase3_support import (
    SECRET,
    ExplodingAI,
    ScriptedProvider,
    Trained,
    make_ai,
    reward_proposal,
    statements_json,
    train_real_run,
)

V = "/api/v1/verification"


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Trained]:
    with train_real_run(tmp_path_factory.mktemp("p3int")) as t:
        yield t


def test_real_training_run_through_intent_verification_and_incident(trained: Trained) -> None:
    client, run_id = trained.client, trained.run_id
    app = client.app

    # 1-2. the genuine persisted evidence, via the Phase 2 builder
    evidence = build_studio_evidence(
        run_id, reader=TrajectoryReader(store_path()), provenance=app.state.services.provenance)
    ev = evidence.payload["execution_evidence"]
    studio_runs = client.get(f"/api/v1/studio/sessions/{trained.session_id}/runs").json()["runs"]
    assert ev["run_id"] == run_id and ev["episodes"] and ev["events"] and ev["checkpoints"]
    assert len(ev["episodes"]) == studio_runs[0]["episode_count"]

    # 3-4. natural-language expectation -> interpretation -> structured requirements
    ok, bad = "the final episode reward must be at least 1", "the final episode reward must be at least 100000"
    statement = f"The agent should do well: {ok}, and {bad}."
    provider = ScriptedProvider(statements_json(ok, bad), [reward_proposal(ok, value=1), reward_proposal(bad, value=100000)])
    app.state.ai_service = make_ai(provider)
    created = client.post(f"{V}/runs/{run_id}/intents", json={"statement": statement, "idempotency_key": "int-1"})
    assert created.status_code == 201, created.text
    intent = created.json()
    assert intent["status"] == "interpreted" and intent["original_text"] == statement
    assert intent["workflow"]["path"][-1] == "persist" and len(intent["requirements"]) == 2
    assert {r["lifecycle_status"] for r in intent["requirements"]} == {"draft"}
    assert all(r["environment_version"] == ev["environment_version"] for r in intent["requirements"])
    assert client.get(f"{V}/intents/{intent['intent_id']}").json()["requirements"] == intent["requirements"]
    replay = client.post(f"{V}/runs/{run_id}/intents", json={"statement": statement, "idempotency_key": "int-1"})
    assert replay.status_code == 200 and replay.json()["intent_id"] == intent["intent_id"]

    # 5. nothing can be verified until the developer confirms
    unconfirmed = client.post(f"{V}/runs/{run_id}/verifications", json={})
    assert unconfirmed.status_code == 409 and unconfirmed.json()["detail"]["error"]["code"] == "conflict"
    rids = [r["requirement_id"] for r in intent["requirements"]]
    for rid in rids:
        confirmed = client.post(f"{V}/requirements/{rid}/confirm")
        assert confirmed.status_code == 200 and confirmed.json()["confirmation_status"] == "confirmed"
    assert {r["lifecycle_status"] for r in client.get(f"{V}/runs/{run_id}/requirements").json()["requirements"]} == {"confirmed"}

    # 6. deterministic verification; from here on a model call would be a bug
    app.state.ai_service = ExplodingAI()
    done = client.post(f"{V}/runs/{run_id}/verifications", json={})
    assert done.status_code == 201, done.text
    verification = done.json()
    vid = verification["verification_id"]
    statuses = {r["requirement_id"]: r["status"] for r in verification["results"]}
    assert statuses == {rids[0]: "pass", rids[1]: "fail"} and verification["overall_status"] == "fail"
    assert verification["traceability"]["run_id"] == run_id and verification["traceability"]["episode_ids"]
    assert verification["workflow"]["path"] == ["load_requirements", "retrieve_evidence", "idempotency", "verify",
                                                "persist", "incident_handoff"]

    # 7-8. persisted and readable; the incident went through the Person 4 public interface
    link = verification["incident"]
    assert link["handoff_status"] == "created" and link["failed_requirement_ids"] == [rids[1]]
    incident = app.state.services.provenance.get_incident(link["incident_id"])
    assert (incident.run_id, incident.verification_id, incident.requirement_id) == (run_id, vid, rids[1])
    assert incident.details["failed_requirements"][0]["expected"] == 100000

    # backend "restart": a second application instance over the same databases
    with TestClient(create_app()) as restarted:
        again = restarted.get(f"{V}/verifications/{vid}")
        assert again.status_code == 200
        body = again.json()
        assert body["overall_status"] == "fail" and body["results"] == verification["results"]
        assert body["incident"]["incident_id"] == link["incident_id"]
        history = restarted.get(f"{V}/runs/{run_id}/verifications").json()
        assert [v["verification_id"] for v in history["verifications"]] == [vid]
        results = restarted.get(f"{V}/verifications/{vid}/results").json()
        assert results["count"] == 2 and all(r["evidence_refs"] for r in results["results"])
        assert restarted.get(f"{V}/requirements/{rids[1]}").json()["lifecycle_status"] == "failed"
        assert restarted.get(f"{V}/requirements/{rids[0]}").json()["lifecycle_status"] == "verified"
        again_incident = restarted.app.state.services.provenance.get_incident(link["incident_id"])
        assert again_incident.verification_id == vid

    # 9. retries are idempotent end to end
    retry = client.post(f"{V}/runs/{run_id}/verifications", json={})
    assert retry.status_code == 200 and retry.json()["verification_id"] == vid and retry.json()["replayed"] is True
    with app.state.database.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM incidents WHERE verification_id = ?", (vid,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM verifications WHERE run_id = ?", (run_id,)).fetchone()[0] == 1

    # nothing secret ever reaches a response
    every = json.dumps([verification, intent, body, history])
    assert SECRET not in every and "Bearer" not in every


def test_http_contract_errors_are_stable_and_leak_nothing(trained: Trained) -> None:
    client = trained.client
    app = client.app
    provider = ScriptedProvider()
    provider.mode = "down"
    app.state.ai_service = make_ai(provider)
    try:
        def code(resp: Any) -> str:
            return resp.json()["detail"]["error"]["code"]

        assert client.post(f"{V}/runs/nope/intents", json={"statement": "x"}).status_code == 404
        assert client.post(f"{V}/runs/{trained.run_id}/intents", json={"statement": ""}).status_code == 422
        assert client.post(f"{V}/runs/{trained.run_id}/intents", json={"statement": "ok", "bogus": 1}).status_code == 422
        assert client.post(f"{V}/runs/{trained.run_id}/intents",
                           json={"statement": "ok", "context": {"api_key": "x"}}).status_code == 422
        assert client.post(f"{V}/runs/bad id!/intents", json={"statement": "ok"}).status_code == 422
        # provider down: the request itself succeeds and records the failure; no requirement, no verdict
        down = client.post(f"{V}/runs/{trained.run_id}/intents", json={"statement": "Make it behave sensibly."})
        assert down.status_code == 201 and down.json()["status"] == "provider_unavailable"
        assert "upstream detail" not in down.text and SECRET not in down.text
        assert code(client.get(f"{V}/intents/missing")) == "not_found"
        assert code(client.get(f"{V}/verifications/missing")) == "not_found"
        assert code(client.get(f"{V}/requirements/missing")) == "not_found"
        assert client.get(f"{V}/runs/nope/verifications").status_code == 404
        assert code(client.post(f"{V}/runs/{trained.run_id}/verifications", json={"requirement_ids": ["ghost"]})) == "conflict"
        assert client.post(f"{V}/runs/{trained.run_id}/verifications", json={"requirement_ids": []}).status_code == 422
        assert client.post(f"{V}/verifications/missing/incident/retry").status_code == 404
        status = client.get(f"{V}/status")
        assert status.status_code == 200 and SECRET not in status.text
    finally:
        app.state.ai_service = None
