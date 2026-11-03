"""Agent brain: real action probabilities / Q-values streamed with each frame."""

from __future__ import annotations

import io
import math
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from stable_baselines3 import PPO

from backend.studio import brain as brain_module
from backend.studio.envs import ENVIRONMENTS

from .test_studio import BASE, _create

SLOW = {"total_timesteps": 200_000, "simulation_speed": 8, "checkpoint_every": 0, "eval_every": 0}


def _frame_with_brain(client: TestClient, sid: str, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        frame = client.get(f"{BASE}/sessions/{sid}").json()["frame"]
        if frame and "brain" in frame:
            return frame
        time.sleep(0.05)
    raise AssertionError("no frame with a brain payload arrived")


def _run(client: TestClient, **kwargs: Any) -> str:
    sid = _create(client, training=kwargs.pop("training", SLOW), **kwargs)
    client.post(f"{BASE}/sessions/{sid}/start")
    return sid


def _stop(client: TestClient, sid: str) -> None:
    client.post(f"{BASE}/sessions/{sid}/stop")
    for _ in range(100):
        if client.get(f"{BASE}/sessions/{sid}").json()["status"] in ("stopped", "completed", "failed"):
            return
        time.sleep(0.1)


def test_the_brain_is_off_by_default_and_frames_stay_small(client: TestClient) -> None:
    sid = _run(client)
    time.sleep(0.6)
    frame = client.get(f"{BASE}/sessions/{sid}").json()["frame"]
    assert "brain" not in frame
    assert client.get(f"{BASE}/sessions/{sid}").json()["controls"]["brain"] is False
    _stop(client, sid)


def test_ppo_streams_real_action_probabilities(client: TestClient) -> None:
    sid = _run(client, agent="PPO")
    assert client.post(f"{BASE}/sessions/{sid}/brain", json={"enabled": True}).status_code == 200
    brain = _frame_with_brain(client, sid)["brain"]
    assert brain["kind"] == "probs" and len(brain["probs"]) == 2
    assert math.isclose(sum(brain["probs"]), 1.0, abs_tol=1e-3) and all(0 <= p <= 1 for p in brain["probs"])
    assert brain["greedy"] == brain["probs"].index(max(brain["probs"]))
    assert brain["executed"] in (0, 1) and "grid" not in brain
    client.post(f"{BASE}/sessions/{sid}/brain", json={"enabled": False})
    time.sleep(0.6)
    assert "brain" not in client.get(f"{BASE}/sessions/{sid}").json()["frame"]
    _stop(client, sid)


def test_dqn_streams_q_values_and_their_softmax(client: TestClient) -> None:
    sid = _run(client, agent="DQN", agent_params={"learning_starts": 50, "buffer_size": 2000})
    client.post(f"{BASE}/sessions/{sid}/brain", json={"enabled": True})
    brain = _frame_with_brain(client, sid)["brain"]
    assert brain["kind"] == "q" and len(brain["q"]) == 2 and brain["probs_from"] == "softmax(q)"
    assert math.isclose(sum(brain["probs"]), 1.0, abs_tol=1e-3)
    assert brain["greedy"] == brain["q"].index(max(brain["q"]))
    _stop(client, sid)


def test_warehouse_brain_includes_a_preference_for_every_free_cell(client: TestClient) -> None:
    sid = _run(client, agent="A2C", environment="warehouse")
    client.post(f"{BASE}/sessions/{sid}/brain", json={"enabled": True})
    frame = _frame_with_brain(client, sid)
    deadline = time.time() + 10
    while "grid" not in frame["brain"] and time.time() < deadline:
        frame = _frame_with_brain(client, sid)
    scene = client.get(f"{BASE}/sessions/{sid}").json()["scene"]
    grid = frame["brain"]["grid"]
    assert len(grid) == scene["rows"] * scene["cols"] - len(scene["obstacles"])
    assert not {(c["row"], c["col"]) for c in grid} & {tuple(o) for o in scene["obstacles"]}
    assert all(len(c["probs"]) == 4 and math.isclose(sum(c["probs"]), 1.0, abs_tol=1e-3) for c in grid)
    _stop(client, sid)


def test_uploaded_models_can_be_inspected_too(client: TestClient) -> None:
    import gymnasium as gym

    buffer = io.BytesIO()
    PPO("MlpPolicy", gym.make("CartPole-v1"), verbose=0, seed=1).save(buffer)
    key = client.post(f"{BASE}/models/upload", params={"filename": "p.zip"}, content=buffer.getvalue()).json()["model"]["key"]
    sid = _run(client, agent=key)
    client.post(f"{BASE}/sessions/{sid}/brain", json={"enabled": True})
    assert _frame_with_brain(client, sid)["brain"]["kind"] == "probs"
    _stop(client, sid)


def test_brain_toggle_rules(client: TestClient) -> None:
    sid = _create(client, training=SLOW)
    assert client.post(f"{BASE}/sessions/{sid}/brain", json={"enabled": True}).status_code == 200  # before start
    assert client.post(f"{BASE}/sessions/{sid}/brain", json={"enabled": "yes"}).status_code == 422
    assert client.post(f"{BASE}/sessions/{sid}/brain", json={"enabled": True, "x": 1}).status_code == 422
    assert client.post(f"{BASE}/sessions/ses_deadbeef/brain", json={"enabled": True}).status_code == 404
    client.post(f"{BASE}/sessions/{sid}/start")
    _stop(client, sid)
    assert client.post(f"{BASE}/sessions/{sid}/brain", json={"enabled": False}).status_code == 409


def test_unsupported_policies_return_nothing_instead_of_guessing() -> None:
    class Opaque:
        pass

    assert brain_module.compute_brain(None, [0.0]) is None
    assert brain_module.compute_brain(object(), None) is None
    with pytest.raises((AttributeError, TypeError)):
        brain_module.compute_brain(Opaque(), [0.0, 0.0, 0.0, 0.0])
    assert brain_module.compute_grid_brain(None, {"rows": 2}) is None


def test_grid_brain_matches_the_environment_layout() -> None:
    definition = ENVIRONMENTS["warehouse"]
    env = definition.make({p.key: p.default for p in definition.params}, 0)
    scene = definition.scene({p.key: p.default for p in definition.params}, env)
    policy = PPO("MlpPolicy", env, verbose=0, seed=0).policy
    grid = brain_module.compute_grid_brain(policy, scene)
    assert grid is not None and len(grid) == len(brain_module.free_cells(scene))
