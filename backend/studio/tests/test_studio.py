"""Studio API tests: validation, lifecycle, idempotency, and real short training runs."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.studio.manager import manager

BASE = "/api/v1/studio"


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("STUDIO_DATA_DIR", str(tmp_path / "studio"))
    monkeypatch.setenv("RL_STUDIO_DATA_ROOT", str(tmp_path / "var"))
    with TestClient(create_app()) as test_client:
        yield test_client
    for session in list(manager._sessions.values()):
        with contextlib.suppress(Exception):
            session.stop()
    manager._sessions.clear()


def _create(client: TestClient, **overrides: Any) -> str:
    body: dict[str, Any] = {
        "agent": "PPO",
        "environment": "cartpole",
        "training": {"total_timesteps": 2000, "simulation_speed": 0, "checkpoint_every": 1000, "eval_every": 1000, "eval_episodes": 2},
    }
    body.update(overrides)
    response = client.post(f"{BASE}/sessions", json=body)
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


def _wait(client: TestClient, sid: str, states: set[str], timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    snap: dict[str, Any] = {}
    while time.time() < deadline:
        snap = client.get(f"{BASE}/sessions/{sid}").json()
        if snap["status"] in states:
            return snap
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {states}; last={snap.get('status')}")


def test_catalog_lists_only_runnable_agents_with_derived_compatibility(client: TestClient) -> None:
    catalog = client.get(f"{BASE}/catalog").json()
    assert {a["key"] for a in catalog["agents"]} == {"PPO", "A2C", "DQN"}
    cartpole = next(e for e in catalog["environments"] if e["key"] == "cartpole")
    assert cartpole["action_space"] == {"type": "discrete", "n": 2}
    assert set(cartpole["compatible_agents"]) == {"PPO", "A2C", "DQN"}


@pytest.mark.parametrize(
    "body, field",
    [
        ({"agent": "SAC", "environment": "cartpole"}, "agent"),
        ({"agent": "PPO", "environment": "doom"}, "environment"),
        ({"agent": "PPO", "environment": "cartpole", "agent_params": {"bogus": 1}}, "agent_params.bogus"),
        ({"agent": "PPO", "environment": "cartpole", "agent_params": {"learning_rate": -1}}, "agent_params.learning_rate"),
        ({"agent": "PPO", "environment": "cartpole", "agent_params": {"batch_size": 2048, "n_steps": 64}}, "agent_params.batch_size"),
        ({"agent": "PPO", "environment": "cartpole", "training": {"total_timesteps": 5}}, "training.total_timesteps"),
        ({"agent": "PPO", "environment": "cartpole", "env_params": {"gravity": "heavy"}}, "env_params.gravity"),
    ],
)
def test_invalid_configuration_is_rejected_with_field_errors(client: TestClient, body: dict[str, Any], field: str) -> None:
    response = client.post(f"{BASE}/sessions", json=body)
    assert response.status_code == 422
    fields = {e["field"] for e in response.json()["error"]["details"]["errors"]}
    assert field in fields


def test_unknown_session_returns_404(client: TestClient) -> None:
    assert client.get(f"{BASE}/sessions/ses_deadbeef").status_code == 404
    assert client.get(f"{BASE}/sessions/..%2F..%2Fetc").status_code == 404


def test_illegal_transitions_are_typed_conflicts(client: TestClient) -> None:
    sid = _create(client)
    assert client.post(f"{BASE}/sessions/{sid}/pause").status_code == 409
    assert client.post(f"{BASE}/sessions/{sid}/stop").status_code == 409


def test_training_completes_with_real_metrics_and_checkpoints(client: TestClient) -> None:
    sid = _create(client)
    assert client.post(f"{BASE}/sessions/{sid}/start").json()["status"] == "running"
    snap = _wait(client, sid, {"completed", "failed"})
    assert snap["status"] == "completed", snap["error"]
    assert snap["progress"]["timestep"] >= 2000
    assert snap["episodes"] and snap["updates"] and snap["evaluations"]
    assert snap["checkpoints"] and all(len(c["sha256"]) == 64 for c in snap["checkpoints"])
    assert all("path" not in c for c in snap["checkpoints"])
    types = {e["type"] for e in client.get(f"{BASE}/sessions/{sid}/events").json()["events"]}
    assert {"lifecycle", "log", "progress", "episodes", "update", "checkpoint", "evaluation"} <= types
    # A completed session cannot be restarted without a reset.
    assert client.post(f"{BASE}/sessions/{sid}/start").status_code == 409
    assert client.post(f"{BASE}/sessions/{sid}/reset").json()["status"] == "initialized"
    assert client.get(f"{BASE}/sessions/{sid}").json()["episodes"] == []


def test_pause_resume_stop_with_idempotency(client: TestClient) -> None:
    sid = _create(client, training={"total_timesteps": 200_000, "simulation_speed": 4, "checkpoint_every": 0, "eval_every": 0})
    client.post(f"{BASE}/sessions/{sid}/start")
    assert client.post(f"{BASE}/sessions/{sid}/pause").status_code == 200
    _wait(client, sid, {"paused"})
    held = client.get(f"{BASE}/sessions/{sid}").json()["progress"]["timestep"]
    time.sleep(0.6)
    assert client.get(f"{BASE}/sessions/{sid}").json()["progress"]["timestep"] == held
    assert client.post(f"{BASE}/sessions/{sid}/pause").json()["idempotent"] is True
    client.post(f"{BASE}/sessions/{sid}/resume")
    _wait(client, sid, {"running"})
    assert client.post(f"{BASE}/sessions/{sid}/reset").status_code == 409
    client.post(f"{BASE}/sessions/{sid}/stop")
    assert _wait(client, sid, {"stopped"})["status"] == "stopped"
    assert client.post(f"{BASE}/sessions/{sid}/stop").json()["idempotent"] is True


def test_only_one_session_may_train_at_a_time(client: TestClient) -> None:
    slow = {"total_timesteps": 200_000, "simulation_speed": 2, "checkpoint_every": 0, "eval_every": 0}
    first, second = _create(client, training=slow), _create(client, training=slow)
    client.post(f"{BASE}/sessions/{first}/start")
    assert client.post(f"{BASE}/sessions/{second}/start").status_code == 409
    client.post(f"{BASE}/sessions/{first}/stop")
    _wait(client, first, {"stopped"})


def test_warehouse_session_reports_scene_and_collisions(client: TestClient) -> None:
    training = {"total_timesteps": 2000, "simulation_speed": 0, "checkpoint_every": 0, "eval_every": 0}
    sid = _create(client, agent="A2C", environment="warehouse", training=training)
    snap = client.get(f"{BASE}/sessions/{sid}").json()
    assert snap["scene"]["rows"] == 6 and snap["scene"]["obstacles"]
    assert any(e["payload"]["message"] == "Session initialized" for e in snap["logs"])
    client.post(f"{BASE}/sessions/{sid}/start")
    done = _wait(client, sid, {"completed", "failed"})
    assert done["status"] == "completed", done["error"]
    assert done["progress"]["collisions"] > 0


def test_websocket_sends_snapshot_then_ordered_events(client: TestClient) -> None:
    sid = _create(client)
    with client.websocket_connect(f"{BASE}/sessions/{sid}/stream") as ws:
        assert ws.receive_json()["type"] == "snapshot"
        client.post(f"{BASE}/sessions/{sid}/start")
        seqs: list[int] = []
        for _ in range(60):
            message = ws.receive_json()
            if message["type"] != "frame":
                seqs.append(message["seq"])
            if len(seqs) >= 5:
                break
        assert len(seqs) >= 5 and seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    _wait(client, sid, {"completed", "failed"})


def test_unknown_websocket_session_is_refused(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"{BASE}/sessions/ses_00000000/stream"):
        pass
