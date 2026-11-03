"""Human-in-the-loop override: manual actions replace the agent's and are tagged source=human."""

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.studio.store import TrajectoryReader

from .test_studio import BASE, _create, _wait

SLOW = {"total_timesteps": 200_000, "simulation_speed": 8, "checkpoint_every": 0, "eval_every": 0}


def _snapshot(client: TestClient, sid: str) -> dict[str, Any]:
    return client.get(f"{BASE}/sessions/{sid}").json()


def _wait_for(client: TestClient, sid: str, predicate: Any, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    snap: dict[str, Any] = {}
    while time.time() < deadline:
        snap = _snapshot(client, sid)
        if predicate(snap):
            return snap
        time.sleep(0.05)
    raise AssertionError(f"condition not met; last status={snap.get('status')}")


def _human_steps(client: TestClient, run_id: str) -> list[dict[str, Any]]:
    return client.get(f"{BASE}/runs/{run_id}/steps", params={"source": "human", "limit": 5000}).json()["steps"]


def _run_with_human_interlude(client: TestClient, agent: str, agent_params: dict[str, Any] | None = None) -> dict[str, Any]:
    sid = _create(client, agent=agent, agent_params=agent_params or {}, training=SLOW)
    client.post(f"{BASE}/sessions/{sid}/start")
    _wait_for(client, sid, lambda s: s["progress"]["timestep"] >= 60)
    assert client.post(f"{BASE}/sessions/{sid}/control", json={"active": True}).status_code == 200
    assert client.post(f"{BASE}/sessions/{sid}/action", json={"action": 1}).json() == {"accepted": True}
    snap = _wait_for(client, sid, lambda s: s["controls"]["human_steps"] >= 5)
    assert snap["frame"]["source"] == "human" and snap["frame"]["action"] == 1
    client.post(f"{BASE}/sessions/{sid}/control", json={"active": False})
    _wait_for(client, sid, lambda s: s["frame"]["source"] == "agent")
    client.post(f"{BASE}/sessions/{sid}/stop")
    final = _wait(client, sid, {"stopped", "failed", "completed"})
    assert final["status"] == "stopped", final["error"]
    return final


def test_manual_actions_replace_the_agent_and_are_tagged_in_the_trajectory(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="backend.studio.session")
    final = _run_with_human_interlude(client, "PPO", {"n_steps": 64, "batch_size": 64})
    human = _human_steps(client, final["run_id"])
    assert len(human) >= 5
    assert {s["action"] for s in human} == {1}  # CartPole keeps pushing the last manual action
    assert all(s["source"] == "human" for s in human)
    everything = client.get(f"{BASE}/runs/{final['run_id']}/steps", params={"limit": 5000}).json()["steps"]
    assert {s["source"] for s in everything} == {"agent", "human"}
    assert any(e["payload"].get("message", "").startswith("Learning from human steps") for e in final["logs"])
    assert "Could not align" not in caplog.text


def test_off_policy_agents_keep_training_through_a_human_interlude(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="backend.studio.session")
    final = _run_with_human_interlude(client, "DQN", {"learning_starts": 50, "buffer_size": 2000})
    assert len(_human_steps(client, final["run_id"])) >= 5
    assert "Could not align" not in caplog.text


def test_one_shot_environments_consume_one_action_per_step(client: TestClient) -> None:
    sid = _create(client, agent="PPO", environment="warehouse", training=SLOW)
    client.post(f"{BASE}/sessions/{sid}/start")
    _wait_for(client, sid, lambda s: s["progress"]["timestep"] >= 40)
    client.post(f"{BASE}/sessions/{sid}/control", json={"active": True})
    sent = [3, 1, 0]
    for count, action in enumerate(sent, start=1):
        assert client.post(f"{BASE}/sessions/{sid}/action", json={"action": action}).status_code == 200
        _wait_for(client, sid, lambda s, c=count: s["controls"]["human_steps"] >= c)
    time.sleep(0.3)  # the environment now waits: no further human steps without further input
    assert _snapshot(client, sid)["controls"]["human_steps"] == 3
    client.post(f"{BASE}/sessions/{sid}/control", json={"active": False})
    client.post(f"{BASE}/sessions/{sid}/stop")
    final = _wait(client, sid, {"stopped", "failed"})
    assert final["status"] == "stopped", final["error"]
    assert [s["action"] for s in _human_steps(client, final["run_id"])] == sent


def test_releasing_control_unblocks_a_waiting_environment(client: TestClient) -> None:
    sid = _create(client, agent="A2C", environment="warehouse", training=SLOW)
    client.post(f"{BASE}/sessions/{sid}/start")
    _wait_for(client, sid, lambda s: s["progress"]["timestep"] >= 40)
    client.post(f"{BASE}/sessions/{sid}/control", json={"active": True})
    time.sleep(0.4)
    held = _snapshot(client, sid)["progress"]["timestep"]
    time.sleep(0.4)
    assert _snapshot(client, sid)["progress"]["timestep"] <= held + 1  # waiting for a human
    client.post(f"{BASE}/sessions/{sid}/control", json={"active": False})
    _wait_for(client, sid, lambda s: s["progress"]["timestep"] > held + 20)
    client.post(f"{BASE}/sessions/{sid}/stop")
    assert _wait(client, sid, {"stopped", "failed"})["status"] == "stopped"


def test_stopping_while_waiting_for_a_human_does_not_hang(client: TestClient) -> None:
    sid = _create(client, agent="PPO", environment="warehouse", training=SLOW)
    client.post(f"{BASE}/sessions/{sid}/start")
    _wait_for(client, sid, lambda s: s["progress"]["timestep"] >= 40)
    client.post(f"{BASE}/sessions/{sid}/control", json={"active": True})
    time.sleep(0.2)
    client.post(f"{BASE}/sessions/{sid}/stop")
    assert _wait(client, sid, {"stopped", "failed"}, timeout=10)["status"] == "stopped"


@pytest.mark.parametrize("action", [2, -1, True, "left", None, 1.5, [1], {"a": 1}])
def test_invalid_actions_are_rejected(client: TestClient, action: Any) -> None:
    sid = _create(client, training=SLOW)
    client.post(f"{BASE}/sessions/{sid}/start")
    client.post(f"{BASE}/sessions/{sid}/control", json={"active": True})
    response = client.post(f"{BASE}/sessions/{sid}/action", json={"action": action})
    assert response.status_code == 422
    client.post(f"{BASE}/sessions/{sid}/stop")


def test_actions_require_active_control_and_a_live_session(client: TestClient) -> None:
    sid = _create(client, training=SLOW)
    assert client.post(f"{BASE}/sessions/{sid}/action", json={"action": 1}).status_code == 409
    client.post(f"{BASE}/sessions/{sid}/start")
    assert client.post(f"{BASE}/sessions/{sid}/action", json={"action": 1}).status_code == 409
    client.post(f"{BASE}/sessions/{sid}/stop")
    _wait(client, sid, {"stopped"})
    assert client.post(f"{BASE}/sessions/{sid}/control", json={"active": True}).status_code == 409
    assert client.post(f"{BASE}/sessions/ses_deadbeef/control", json={"active": True}).status_code == 404
    assert client.post(f"{BASE}/sessions/{sid}/control", json={"active": True, "x": 1}).status_code == 422


def test_websocket_action_messages_are_acknowledged_or_rejected(client: TestClient) -> None:
    sid = _create(client, training=SLOW)
    client.post(f"{BASE}/sessions/{sid}/start")
    with client.websocket_connect(f"{BASE}/sessions/{sid}/stream") as ws:
        assert ws.receive_json()["type"] == "snapshot"

        def reply_to(message: dict[str, Any]) -> dict[str, Any]:
            ws.send_json(message)
            for _ in range(200):
                received = ws.receive_json()
                if received["type"] in ("action_ack", "action_rejected"):
                    return received
            raise AssertionError("no reply")

        assert reply_to({"type": "action", "action": 1})["type"] == "action_rejected"  # control not taken yet
        client.post(f"{BASE}/sessions/{sid}/control", json={"active": True})
        assert reply_to({"type": "action", "action": 0}) == {"type": "action_ack", "accepted": True}
        assert reply_to({"type": "action", "action": 9})["type"] == "action_rejected"
    client.post(f"{BASE}/sessions/{sid}/stop")
    _wait(client, sid, {"stopped", "failed"})


def test_control_state_is_part_of_the_snapshot_and_event_stream(client: TestClient) -> None:
    sid = _create(client, training=SLOW)
    assert _snapshot(client, sid)["controls"] == {"human": False, "human_steps": 0, "brain": False}
    client.post(f"{BASE}/sessions/{sid}/start")
    client.post(f"{BASE}/sessions/{sid}/control", json={"active": True})
    assert _snapshot(client, sid)["controls"]["human"] is True
    events = client.get(f"{BASE}/sessions/{sid}/events").json()["events"]
    assert any(e["type"] == "control" and e["payload"]["human"] is True for e in events)
    client.post(f"{BASE}/sessions/{sid}/stop")
    _wait(client, sid, {"stopped"})
    assert _snapshot(client, sid)["controls"]["human"] is False  # released when the run ends


def test_old_trajectory_databases_are_migrated_to_record_the_action_source(tmp_path) -> None:
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE steps (run_id TEXT NOT NULL, step_index INTEGER NOT NULL, episode INTEGER NOT NULL,
            episode_step INTEGER NOT NULL, ts REAL NOT NULL, obs BLOB, action TEXT NOT NULL, reward REAL NOT NULL,
            terminated INTEGER NOT NULL, truncated INTEGER NOT NULL, next_obs BLOB, PRIMARY KEY (run_id, step_index)) WITHOUT ROWID;
        INSERT INTO steps VALUES ('ses_00000001_r1', 1, 1, 1, 0.0, NULL, '1', 1.0, 0, 0, NULL);
        """
    )
    conn.commit()
    conn.close()
    steps = TrajectoryReader(path).steps("ses_00000001_r1", episode=None, offset=0, limit=10)
    assert steps[0]["source"] == "agent"
    assert TrajectoryReader(path).steps("ses_00000001_r1", episode=None, offset=0, limit=10, source="human") == []
