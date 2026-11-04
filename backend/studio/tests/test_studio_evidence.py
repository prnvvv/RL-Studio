"""Evidence built from a real persisted Studio run feeds the real verification engine."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.database.config import DatabaseConfig
from backend.database.connection import Database
from backend.provenance.service import ProvenanceService
from backend.studio.session import store_path
from backend.studio.store import TrajectoryReader
from backend.verification.agent.agent_controller import VerificationAgentController
from backend.verification.input.studio_evidence import (
    StudioRunNotFoundError,
    build_studio_evidence,
)
from backend.verification.storage.verification_store import InMemoryVerificationStore

from .test_studio import BASE, _create, _wait

TRAINING = {"total_timesteps": 2000, "simulation_speed": 0, "checkpoint_every": 1000, "eval_every": 1000, "eval_episodes": 2}


def _train(client: TestClient, **overrides) -> dict:
    sid = _create(client, training=TRAINING, **overrides)
    client.post(f"{BASE}/sessions/{sid}/start")
    snap = _wait(client, sid, {"completed", "failed"})
    assert snap["status"] == "completed", snap["error"]
    return snap


def _build(run_id: str, **kwargs):
    return build_studio_evidence(
        run_id,
        reader=TrajectoryReader(store_path()),
        provenance=ProvenanceService(Database(DatabaseConfig.from_env())),
        **kwargs,
    )


def test_evidence_reflects_persisted_run_and_validates_against_schema(client: TestClient) -> None:
    snap = _train(client)
    result = _build(snap["run_id"], developer_intent="the agent should balance the pole")
    ev = result.payload["execution_evidence"]
    assert ev["run_id"] == snap["run_id"] and ev["environment_version"] == "CartPole-v1"
    runs = client.get(f"{BASE}/sessions/{snap['session_id']}/runs").json()["runs"]
    assert ev["training_summary"]["episode_count"] == runs[0]["episode_count"] == len(ev["episodes"])
    assert {c["checkpoint_id"] for c in ev["checkpoints"]} == {
        c["checkpoint_id"] for c in client.get(f"{BASE}/runs/{snap['run_id']}/checkpoints").json()["checkpoints"]
    }
    assert "expected" not in ev["reward"], "an expected reward must never be derived from observed data"
    assert result.to_verification_input().developer_intent == "the agent should balance the pole"


def test_events_over_the_engine_bound_are_reported_incomplete_not_complete(client: TestClient) -> None:
    snap = _train(client)
    result = _build(snap["run_id"])
    ev = result.payload["execution_evidence"]
    assert len(ev["events"]) <= 50
    if len(ev["episodes"]) > 40:
        assert ev["evidence_complete"] is False
        assert any(m.startswith("events_truncated") for m in result.missing_evidence)


def test_expected_reward_is_only_present_when_supplied(client: TestClient) -> None:
    snap = _train(client)
    ev = _build(snap["run_id"], expected_reward=1.0).payload["execution_evidence"]
    assert ev["reward"]["expected"] == 1.0


def test_incomplete_evidence_never_verifies_as_pass(client: TestClient) -> None:
    snap = _train(client)
    result = _build(snap["run_id"], developer_intent="the agent should balance the pole")
    out = VerificationAgentController(model_client=None, storage=InMemoryVerificationStore()).run_verification_output(
        result.to_verification_input()
    )
    assert out["overall_status"] != "pass"


def test_unknown_run_is_a_typed_error(client: TestClient) -> None:
    with pytest.raises(StudioRunNotFoundError):
        _build("does_not_exist")


def test_run_missing_from_provenance_is_flagged(client: TestClient) -> None:
    snap = _train(client)
    result = build_studio_evidence(
        snap["run_id"], reader=TrajectoryReader(store_path()),
        provenance=ProvenanceService(Database(DatabaseConfig.from_env())),
    )
    assert "run_not_registered_in_provenance" not in result.missing_evidence
    # a run that exists in Studio but was never registered with provenance is not "complete"
    other = DatabaseConfig.for_tests(store_path().parent / "other")
    empty = Database(other)
    empty.initialize()
    flagged = build_studio_evidence(
        snap["run_id"], reader=TrajectoryReader(store_path()), provenance=ProvenanceService(empty)
    )
    assert "run_not_registered_in_provenance" in flagged.missing_evidence
    assert flagged.payload["execution_evidence"]["evidence_complete"] is False
