"""Real Studio training runs publish canonical events and register provenance (no mocks)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.database.config import DatabaseConfig
from backend.database.connection import Database
from backend.events.service import EventPublisher, stable_event_id
from backend.provenance.service import ProvenanceService
from backend.studio.provenance_bridge import (
    config_fingerprint,
    resolve_environment_version,
)

from .test_studio import BASE, _create, _wait

TRAINING = {"total_timesteps": 2000, "simulation_speed": 0, "checkpoint_every": 1000, "eval_every": 1000, "eval_episodes": 2}


def _train(client: TestClient) -> dict:
    sid = _create(client, training=TRAINING)
    client.post(f"{BASE}/sessions/{sid}/start")
    snap = _wait(client, sid, {"completed", "failed"})
    assert snap["status"] == "completed", snap["error"]
    return snap


def test_training_publishes_canonical_events_persisted_in_order(client: TestClient) -> None:
    snap = _train(client)
    run_id = snap["run_id"]
    events = EventPublisher.list_run_events(run_id)
    types = [e.event_type for e in events]
    assert types[0] == "run_started" and types[-1] == "run_completed"
    assert "episode_end" in types and "checkpoint_saved" in types
    assert len({e.event_id for e in events}) == len(events)
    assert [e.timestamp for e in events] == sorted(e.timestamp for e in events)

    episode_events = [e for e in events if e.event_type == "episode_end"]
    runs = client.get(f"{BASE}/sessions/{snap['session_id']}/runs").json()["runs"]
    assert len(episode_events) == runs[0]["episode_count"]
    first = episode_events[0].model_dump()
    assert first["run_id"] == run_id and first["environment_id"] == "cartpole"
    assert first["agent_id"] == "PPO" and first["reward"] is not None
    assert first["terminated"] is not None and first["truncated"] is not None
    assert first["episode_id"] == f"{run_id}_e1"


def test_environment_version_comes_from_the_environment_implementation(client: TestClient) -> None:
    snap = _train(client)
    started = EventPublisher.list_run_events(snap["run_id"])[0]
    assert started.environment_version == "CartPole-v1"
    runs = ProvenanceService(Database(DatabaseConfig.from_env())).database
    with runs.read() as conn:
        row = conn.execute("SELECT environment_id, environment_version FROM runs WHERE run_id = ?", (snap["run_id"],)).fetchone()
    assert (row["environment_id"], row["environment_version"]) == ("cartpole", "CartPole-v1")


def test_run_and_checkpoints_are_registered_with_provenance(client: TestClient) -> None:
    snap = _train(client)
    run_id = snap["run_id"]
    service = ProvenanceService(Database(DatabaseConfig.from_env()))
    artifacts = service.list_run_artifacts(run_id)
    studio_checkpoints = client.get(f"{BASE}/runs/{run_id}/checkpoints").json()["checkpoints"]
    assert artifacts.count == len(studio_checkpoints) >= 1
    by_id = {a.artifact_id: a for a in artifacts.artifacts}
    for ckpt in studio_checkpoints:
        art = by_id[ckpt["checkpoint_id"]]
        assert art.artifact_hash == ckpt["sha256"]
        assert art.integrity_status == "verified" and art.artifact_status == "available"
        assert art.environment_version == "CartPole-v1" and art.run_id == run_id


def test_event_publishing_is_idempotent_and_survives_a_fresh_connection(client: TestClient) -> None:
    snap = _train(client)
    run_id = snap["run_id"]
    before = EventPublisher.list_run_events(run_id)
    again = EventPublisher.publish(
        "episode_end", run_id, idempotency_key=f"{run_id}:episode:1", environment_id="cartpole"
    )
    assert again == stable_event_id(f"{run_id}:episode:1")
    assert len(EventPublisher.list_run_events(run_id)) == len(before)
    # a brand-new Database handle (as after a process restart) sees the same persisted events
    import backend.events.service as ev

    ev.configure(None)
    assert [e.event_id for e in EventPublisher.list_run_events(run_id)] == [e.event_id for e in before]


def test_helpers() -> None:
    assert config_fingerprint({"a": 1, "b": 2}) == config_fingerprint({"b": 2, "a": 1})

    class NoVersion:
        pass

    assert resolve_environment_version(NoVersion()) is None
