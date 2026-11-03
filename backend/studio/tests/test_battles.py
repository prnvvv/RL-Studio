"""Algorithm battles: two sessions, one environment, one seed, trained concurrently."""

from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from backend.studio.manager import manager

from .test_studio import BASE, _wait

FAST = {"total_timesteps": 1500, "simulation_speed": 0, "checkpoint_every": 0, "eval_every": 0, "seed": 7}
SLOW = {"total_timesteps": 200_000, "simulation_speed": 4, "checkpoint_every": 0, "eval_every": 0, "seed": 7}


def _battle_body(training: dict[str, Any] = FAST, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "environment": "cartpole",
        "training": training,
        "a": {"agent": "PPO", "agent_params": {"n_steps": 64, "batch_size": 64}},
        "b": {"agent": "DQN", "agent_params": {"learning_starts": 100, "buffer_size": 2000}},
    }
    body.update(overrides)
    return body


def _create(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    response = client.post(f"{BASE}/battles", json=_battle_body(**kwargs))
    assert response.status_code == 201, response.text
    return response.json()


def _wait_battle(client: TestClient, battle: dict[str, Any], states: set[str], timeout: float = 90.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    snap: dict[str, Any] = {}
    while time.time() < deadline:
        snap = client.get(f"{BASE}/battles/{battle['battle_id']}").json()
        if snap["a"]["status"] in states and snap["b"]["status"] in states:
            return snap
        time.sleep(0.1)
    raise AssertionError(f"timed out; last={snap['a']['status']}/{snap['b']['status']}")


def test_a_battle_creates_two_sessions_on_the_same_environment_and_seed(client: TestClient) -> None:
    battle = _create(client)
    a, b = battle["a"], battle["b"]
    assert battle["battle_id"].startswith("bat_")
    assert (a["agent"], b["agent"]) == ("PPO", "DQN")
    assert a["session_id"] != b["session_id"]
    assert a["battle"] == {"battle_id": battle["battle_id"], "side": "a"} and b["battle"]["side"] == "b"
    assert a["config"]["environment"] == b["config"]["environment"] == "cartpole"
    assert a["config"]["env_params"] == b["config"]["env_params"]
    assert a["config"]["training"] == b["config"]["training"] and a["config"]["training"]["seed"] == 7
    assert a["scene"] == b["scene"]
    assert battle["comparison"]["same_environment"] and battle["comparison"]["same_seed"]


def test_both_sides_train_concurrently_and_are_compared_from_real_progress(client: TestClient) -> None:
    battle = _create(client)
    assert client.post(f"{BASE}/battles/{battle['battle_id']}/start").status_code == 200
    final = _wait_battle(client, battle, {"completed", "failed"})
    assert final["a"]["status"] == final["b"]["status"] == "completed", (final["a"]["error"], final["b"]["error"])
    metrics = final["comparison"]["metrics"]
    for side in ("a", "b"):
        assert metrics[side]["timestep"] >= 1500 and metrics[side]["episodes"] > 0
        assert metrics[side]["reward_per_step"] is not None
        assert metrics[side]["current_reward_avg"] == final[side]["progress"]["current_reward_avg"]
    expected = "a" if metrics["a"]["current_reward_avg"] > metrics["b"]["current_reward_avg"] else "b"
    if metrics["a"]["current_reward_avg"] != metrics["b"]["current_reward_avg"]:
        assert final["comparison"]["leader"] == expected
    # Both runs were persisted independently and started from the same seeded observation.
    runs = {side: final[side]["run_id"] for side in ("a", "b")}
    first = {
        side: client.get(f"{BASE}/runs/{run}/steps", params={"limit": 1}).json()["steps"][0]["observation"]
        for side, run in runs.items()
    }
    assert first["a"] == first["b"]


def test_battle_commands_apply_to_both_sides(client: TestClient) -> None:
    battle = _create(client, training=SLOW)
    bid = battle["battle_id"]
    started = client.post(f"{BASE}/battles/{bid}/start").json()
    assert started["a"]["status"] == started["b"]["status"] == "running"
    assert client.post(f"{BASE}/battles/{bid}/pause").status_code == 200
    paused = _wait_battle(client, battle, {"paused"})
    assert paused["a"]["status"] == paused["b"]["status"] == "paused"
    assert client.post(f"{BASE}/battles/{bid}/speed", json={"speed": 8}).status_code == 200
    assert client.get(f"{BASE}/battles/{bid}").json()["a"]["progress"]["speed"] == 8
    assert client.post(f"{BASE}/battles/{bid}/resume").status_code == 200
    _wait_battle(client, battle, {"running"})
    assert client.post(f"{BASE}/battles/{bid}/stop").status_code == 200
    _wait_battle(client, battle, {"stopped"})
    reset = client.post(f"{BASE}/battles/{bid}/reset").json()
    assert reset["a"]["status"] == reset["b"]["status"] == "initialized"


def test_only_one_battle_or_session_trains_at_a_time(client: TestClient) -> None:
    first = _create(client, training=SLOW)
    second = _create(client, training=SLOW)
    client.post(f"{BASE}/battles/{first['battle_id']}/start")
    assert client.post(f"{BASE}/battles/{second['battle_id']}/start").status_code == 409
    solo = client.post(f"{BASE}/sessions", json={"agent": "PPO", "environment": "cartpole", "training": SLOW}).json()
    assert client.post(f"{BASE}/sessions/{solo['session_id']}/start").status_code == 409
    client.post(f"{BASE}/battles/{first['battle_id']}/stop")
    _wait_battle(client, first, {"stopped"})


def test_a_running_solo_session_blocks_a_battle(client: TestClient) -> None:
    solo = client.post(f"{BASE}/sessions", json={"agent": "PPO", "environment": "cartpole", "training": SLOW}).json()
    client.post(f"{BASE}/sessions/{solo['session_id']}/start")
    battle = _create(client, training=SLOW)
    assert client.post(f"{BASE}/battles/{battle['battle_id']}/start").status_code == 409
    client.post(f"{BASE}/sessions/{solo['session_id']}/stop")
    _wait(client, solo["session_id"], {"stopped"})


def test_invalid_sides_create_nothing(client: TestClient) -> None:
    before = len(manager._sessions)
    bad_b = client.post(f"{BASE}/battles", json=_battle_body(b={"agent": "SAC"}))
    assert bad_b.status_code == 422 and bad_b.json()["error"]["details"]["side"] == "b"
    bad_params = client.post(f"{BASE}/battles", json=_battle_body(a={"agent": "PPO", "agent_params": {"bogus": 1}}))
    assert bad_params.status_code == 422 and bad_params.json()["error"]["details"]["side"] == "a"
    assert client.post(f"{BASE}/battles", json={"environment": "cartpole", "a": {"agent": "PPO"}}).status_code == 422
    assert len(manager._sessions) == before


def test_unknown_battles_and_double_start(client: TestClient) -> None:
    assert client.get(f"{BASE}/battles/bat_deadbeef").status_code == 404
    assert client.post(f"{BASE}/battles/..%2Fx/start").status_code == 404
    battle = _create(client, training=SLOW)
    assert client.post(f"{BASE}/battles/{battle['battle_id']}/start").status_code == 200
    assert client.post(f"{BASE}/battles/{battle['battle_id']}/start").status_code == 409
    client.post(f"{BASE}/battles/{battle['battle_id']}/stop")
    _wait_battle(client, battle, {"stopped"})
    assert client.post(f"{BASE}/battles/{battle['battle_id']}/pause").status_code == 409  # neither side can pause


def test_each_side_streams_independently(client: TestClient) -> None:
    battle = _create(client, training=SLOW)
    streams = []
    for side in ("a", "b"):
        with client.websocket_connect(f"{BASE}/sessions/{battle[side]['session_id']}/stream") as ws:
            snapshot = ws.receive_json()
            streams.append(snapshot["payload"]["battle"]["side"])
    assert streams == ["a", "b"]
