"""Chaos Monkey: stochastic and API-triggered disturbances, logged as FAULT events."""

from __future__ import annotations

import time
from typing import Any

import gymnasium as gym
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.studio.controls import RuntimeControls
from backend.studio.wrappers import ChaosEnv

from .test_studio import BASE, _create

SLOW = {"total_timesteps": 200_000, "simulation_speed": 8, "checkpoint_every": 0, "eval_every": 0}


def _start(client: TestClient, **kwargs: Any) -> str:
    sid = _create(client, training=SLOW, **kwargs)
    client.post(f"{BASE}/sessions/{sid}/start")
    return sid


def _stop(client: TestClient, sid: str) -> dict[str, Any]:
    client.post(f"{BASE}/sessions/{sid}/stop")
    for _ in range(100):
        snap = client.get(f"{BASE}/sessions/{sid}").json()
        if snap["status"] in ("stopped", "completed", "failed"):
            return snap
        time.sleep(0.1)
    raise AssertionError("did not stop")


def _fault_logs(client: TestClient, sid: str) -> list[dict[str, Any]]:
    events = client.get(f"{BASE}/sessions/{sid}/events", params={"limit": 2000}).json()["events"]
    return [e["payload"] for e in events if e["type"] == "log" and e["payload"]["category"] == "FAULT"]


def _wait_until(predicate: Any, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


# ------------------------------------------------------------------ wrapper unit tests


def _wrapped(seed: int = 3, noise: tuple[float, ...] = (0.25, 0.5, 0.05, 0.5)) -> tuple[ChaosEnv, RuntimeControls]:
    controls = RuntimeControls()
    env = ChaosEnv(gym.make("CartPole-v1"), controls, seed, noise)
    env.reset(seed=seed)
    return env, controls


def test_nothing_happens_while_chaos_is_off() -> None:
    env, _ = _wrapped()
    for _ in range(50):
        _, _, terminated, truncated, info = env.step(1)
        assert info["chaos"] == []
        if terminated or truncated:
            env.reset()


def test_sensor_noise_perturbs_only_the_observation_by_the_configured_amount() -> None:
    clean, _ = _wrapped(seed=1)
    noisy, controls = _wrapped(seed=1)
    controls.configure_chaos(True, 1.0, ("sensor_noise",))
    deltas = []
    for _ in range(100):
        obs_clean, *_ = clean.step(1)
        obs_noisy, _, _, _, info = noisy.step(1)
        deltas.append(obs_noisy - obs_clean)
        assert info["chaos"][0]["kind"] == "sensor_noise"
        if np.abs(obs_clean).max() > 1.5:
            break
    # The underlying state evolves identically, so the difference is pure sensor noise.
    spread = np.std(np.array(deltas), axis=0)
    assert np.all(spread > 0.5 * np.array([0.25, 0.5, 0.05, 0.5]))
    assert np.all(spread < 2.0 * np.array([0.25, 0.5, 0.05, 0.5]))


def test_perturbations_are_reproducible_for_a_seed() -> None:
    def run() -> list[Any]:
        env, controls = _wrapped(seed=11)
        controls.configure_chaos(True, 1.0, ("slip", "impulse", "sensor_noise"))
        trace = []
        for _ in range(60):
            obs, _, terminated, truncated, info = env.step(0)
            trace.append((obs.tolist(), [e["kind"] for e in info["chaos"]]))
            if terminated or truncated:
                env.reset()
        return trace

    assert run() == run()


def test_a_forced_trigger_fires_exactly_once_even_with_chaos_off() -> None:
    env, controls = _wrapped()
    controls.trigger_chaos("impulse")
    _, _, _, _, first = env.step(1)
    _, _, _, _, second = env.step(1)
    assert [e["kind"] for e in first["chaos"]] == ["impulse"] and first["chaos"][0]["forced"] is True
    assert second["chaos"] == []


def test_slip_replaces_the_executed_action() -> None:
    env, controls = _wrapped()
    controls.trigger_chaos("slip")
    _, _, _, _, info = env.step(1)
    event = info["chaos"][0]
    assert event["kind"] == "slip" and event["intended"] == 1 and event["executed"] in (0, 1)


# ------------------------------------------------------------------ API


def test_chaos_mode_injects_disturbances_logs_them_and_stores_them_with_the_steps(client: TestClient) -> None:
    sid = _start(client)
    response = client.post(f"{BASE}/sessions/{sid}/chaos", json={"enabled": True, "intensity": 0.9, "kinds": ["impulse", "slip"]})
    assert response.status_code == 200
    _wait_until(lambda: client.get(f"{BASE}/sessions/{sid}").json()["controls"]["chaos"]["events"] >= 3)
    snap = _stop(client, sid)
    chaos = snap["controls"]["chaos"]
    assert chaos["enabled"] is True and chaos["intensity"] == 0.9 and chaos["kinds"] == ["impulse", "slip"]
    faults = _fault_logs(client, sid)
    assert any("Chaos mode enabled" in f["message"] for f in faults)
    assert any(f["message"].startswith("Chaos injected:") and f["level"] == "WARNING" for f in faults)
    steps = client.get(f"{BASE}/runs/{snap['run_id']}/steps", params={"limit": 5000}).json()["steps"]
    marked = [s for s in steps if s["chaos"]]
    assert marked and {k for s in marked for k in s["chaos"]} <= {"impulse", "slip"}


def test_disabled_chaos_never_disturbs_the_run(client: TestClient) -> None:
    sid = _start(client)
    time.sleep(1.0)
    snap = _stop(client, sid)
    assert snap["controls"]["chaos"]["events"] == 0
    assert _fault_logs(client, sid) == []
    steps = client.get(f"{BASE}/runs/{snap['run_id']}/steps", params={"limit": 5000}).json()["steps"]
    assert not any(s["chaos"] for s in steps)


def test_an_api_trigger_injects_one_disturbance_with_chaos_off(client: TestClient) -> None:
    sid = _start(client)
    time.sleep(0.4)
    assert client.post(f"{BASE}/sessions/{sid}/chaos/trigger", json={"kind": "impulse"}).status_code == 200
    _wait_until(lambda: client.get(f"{BASE}/sessions/{sid}").json()["controls"]["chaos"]["events"] == 1)
    time.sleep(0.5)
    snap = _stop(client, sid)
    assert snap["controls"]["chaos"]["events"] == 1
    assert any("triggered manually" in f["message"] for f in _fault_logs(client, sid))
    steps = client.get(f"{BASE}/runs/{snap['run_id']}/steps", params={"limit": 5000}).json()["steps"]
    assert sum(1 for s in steps if s["chaos"] == ["impulse"]) == 1


def test_sensor_noise_is_counted_not_logged_per_step(client: TestClient) -> None:
    sid = _start(client)
    client.post(f"{BASE}/sessions/{sid}/chaos", json={"enabled": True, "intensity": 0.5, "kinds": ["sensor_noise"]})
    _wait_until(lambda: client.get(f"{BASE}/sessions/{sid}").json()["controls"]["chaos"]["noise_steps"] > 20)
    snap = _stop(client, sid)
    assert snap["controls"]["chaos"]["events"] == 0
    assert len([f for f in _fault_logs(client, sid) if f["message"].startswith("Chaos injected")]) == 0


def test_warehouse_supports_slip_and_noise_but_not_physics_impulses(client: TestClient) -> None:
    catalog = client.get(f"{BASE}/catalog").json()
    kinds = {e["key"]: e["chaos_kinds"] for e in catalog["environments"]}
    assert kinds["cartpole"] == ["impulse", "sensor_noise", "slip"]
    assert kinds["warehouse"] == ["slip", "sensor_noise"]
    sid = _start(client, agent="PPO", environment="warehouse")
    assert client.post(f"{BASE}/sessions/{sid}/chaos", json={"enabled": True, "kinds": ["impulse"]}).status_code == 422
    assert client.post(f"{BASE}/sessions/{sid}/chaos/trigger", json={"kind": "impulse"}).status_code == 422
    assert client.post(f"{BASE}/sessions/{sid}/chaos", json={"enabled": True, "intensity": 0.8, "kinds": ["slip"]}).status_code == 200
    _wait_until(lambda: client.get(f"{BASE}/sessions/{sid}").json()["controls"]["chaos"]["events"] >= 1)
    _stop(client, sid)


@pytest.mark.parametrize("body", [{"intensity": 1.5}, {"intensity": -0.1}, {"enabled": "yes"}, {"kinds": ["meteor"]}, {"bogus": 1}])
def test_invalid_chaos_settings_are_rejected(client: TestClient, body: dict[str, Any]) -> None:
    sid = _start(client)
    assert client.post(f"{BASE}/sessions/{sid}/chaos", json=body).status_code == 422
    _stop(client, sid)


def test_chaos_state_rules(client: TestClient) -> None:
    sid = _create(client, training=SLOW)
    assert client.post(f"{BASE}/sessions/{sid}/chaos/trigger", json={"kind": "impulse"}).status_code == 409  # not running
    assert client.post(f"{BASE}/sessions/{sid}/chaos", json={"enabled": True}).status_code == 200  # can be set before start
    client.post(f"{BASE}/sessions/{sid}/start")
    _stop(client, sid)
    assert client.post(f"{BASE}/sessions/{sid}/chaos", json={"enabled": False}).status_code == 409
    assert client.post(f"{BASE}/sessions/ses_deadbeef/chaos", json={"enabled": True}).status_code == 404


def test_old_databases_gain_the_chaos_column(tmp_path) -> None:
    import sqlite3

    from backend.studio.store import TrajectoryReader

    path = tmp_path / "v2.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE steps (run_id TEXT NOT NULL, step_index INTEGER NOT NULL, episode INTEGER NOT NULL,
            episode_step INTEGER NOT NULL, ts REAL NOT NULL, obs BLOB, action TEXT NOT NULL, reward REAL NOT NULL,
            terminated INTEGER NOT NULL, truncated INTEGER NOT NULL, next_obs BLOB,
            source TEXT NOT NULL DEFAULT 'agent', PRIMARY KEY (run_id, step_index)) WITHOUT ROWID;
        INSERT INTO steps VALUES ('ses_00000001_r1', 1, 1, 1, 0.0, NULL, '1', 1.0, 0, 0, NULL, 'agent');
        """
    )
    conn.commit()
    conn.close()
    step = TrajectoryReader(path).steps("ses_00000001_r1", episode=None, offset=0, limit=5)[0]
    assert step["chaos"] == [] and step["source"] == "agent"
