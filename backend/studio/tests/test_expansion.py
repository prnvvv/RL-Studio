"""New algorithms (SAC, TD3, PPO-LSTM), new environments, and live environment dynamics.

Everything here trains or steps the real Stable-Baselines3 models and Gymnasium simulators.
Box2D-backed environments are skipped (never faked) when Box2D is not installed.
"""

from __future__ import annotations

import importlib.util
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.studio.envs import ENVIRONMENTS
from backend.studio.params import validate_params

from .test_studio import BASE, _create, _wait

HAS_BOX2D = importlib.util.find_spec("Box2D") is not None
HAS_CONTRIB = importlib.util.find_spec("sb3_contrib") is not None
needs_box2d = pytest.mark.skipif(not HAS_BOX2D, reason="Box2D is not installed")
needs_contrib = pytest.mark.skipif(not HAS_CONTRIB, reason="sb3-contrib is not installed")

QUICK = {"total_timesteps": 1500, "simulation_speed": 0, "checkpoint_every": 0, "eval_every": 1000, "eval_episodes": 1}
SMALL_REPLAY = {"learning_starts": 100, "buffer_size": 2000, "batch_size": 32}


def _events(client: TestClient, sid: str, kind: str) -> list[dict[str, Any]]:
    events = client.get(f"{BASE}/sessions/{sid}/events", params={"limit": 2000}).json()["events"]
    return [e["payload"] for e in events if e["type"] == kind]


def _env(key: str, **overrides: Any):
    definition = ENVIRONMENTS[key]
    params = validate_params(definition.params, overrides, scope="env_params")
    return definition, params, definition.make(params, 0)


# ------------------------------------------------------------------ catalog


def test_catalog_lists_the_new_algorithms_and_derives_compatibility_from_real_spaces(client: TestClient) -> None:
    catalog = client.get(f"{BASE}/catalog").json()
    agents = {a["key"]: a for a in catalog["agents"]}
    envs = {e["key"]: e for e in catalog["environments"]}
    assert {"SAC", "TD3"} <= set(agents)
    assert agents["SAC"]["family"] == agents["TD3"]["family"] == "off-policy"
    assert agents["SAC"]["action_spaces"] == agents["TD3"]["action_spaces"] == ["box"]
    assert set(envs) >= {"cartpole", "warehouse", "mountaincar", "lunarlander", "lunarlander_continuous", "bipedalwalker"}
    assert envs["mountaincar"]["action_space"]["type"] == "discrete"
    assert "SAC" not in envs["cartpole"]["compatible_agents"] and "DQN" not in envs["bipedalwalker"]["compatible_agents"]
    if HAS_BOX2D:
        assert envs["bipedalwalker"]["action_space"]["type"] == "box"
        assert {"SAC", "TD3"} <= set(envs["bipedalwalker"]["compatible_agents"])
        assert envs["lunarlander"]["available"] is True
    else:
        assert envs["bipedalwalker"]["available"] is False and "Box2D" in envs["bipedalwalker"]["unavailable_reason"]
    if HAS_CONTRIB:
        assert agents["PPO_LSTM"]["name"] == "PPO-LSTM" and set(agents["PPO_LSTM"]["action_spaces"]) == {"discrete", "box"}


def test_incompatible_pairings_are_rejected(client: TestClient) -> None:
    body = {"agent": "SAC", "environment": "cartpole", "training": QUICK}
    assert client.post(f"{BASE}/sessions", json=body).status_code == 422
    body = {"agent": "DQN", "environment": "mountaincar", "training": QUICK, "agent_params": SMALL_REPLAY}
    assert client.post(f"{BASE}/sessions", json=body).status_code == 201


@pytest.mark.skipif(HAS_BOX2D, reason="only meaningful when Box2D is missing")
def test_environments_needing_a_missing_dependency_are_refused_with_the_reason(client: TestClient) -> None:
    response = client.post(f"{BASE}/sessions", json={"agent": "PPO", "environment": "lunarlander", "training": QUICK})
    assert response.status_code == 422 and "Box2D" in response.text


# ------------------------------------------------------------------ real training


@pytest.mark.parametrize(
    ("agent", "environment", "agent_params", "metrics"),
    [
        pytest.param("PPO", "mountaincar", {"n_steps": 128, "batch_size": 64}, {"policy_loss", "value_loss"}, id="ppo-mountaincar"),
        pytest.param("DQN", "mountaincar", SMALL_REPLAY, {"loss"}, id="dqn-mountaincar"),
        pytest.param("PPO_LSTM", "cartpole", {"n_steps": 128, "batch_size": 64}, {"policy_loss", "value_loss"}, id="lstm-cartpole", marks=needs_contrib),
        pytest.param("A2C", "lunarlander", {}, {"policy_loss", "value_loss"}, id="a2c-lunarlander", marks=needs_box2d),
        pytest.param("PPO_LSTM", "lunarlander", {"n_steps": 128, "batch_size": 64}, {"policy_loss"}, id="lstm-lunarlander", marks=[needs_box2d, needs_contrib]),
        pytest.param("SAC", "lunarlander_continuous", SMALL_REPLAY, {"actor_loss", "critic_loss"}, id="sac-lunarlander-continuous", marks=needs_box2d),
        pytest.param("TD3", "bipedalwalker", SMALL_REPLAY, {"actor_loss", "critic_loss"}, id="td3-bipedalwalker", marks=needs_box2d),
    ],
)
def test_new_combinations_really_train(client: TestClient, agent: str, environment: str, agent_params: dict, metrics: set[str]) -> None:
    sid = _create(client, agent=agent, environment=environment, agent_params=agent_params, training=QUICK)
    assert client.post(f"{BASE}/sessions/{sid}/start").status_code == 200
    snap = _wait(client, sid, {"completed", "failed", "stopped"}, timeout=240)
    assert snap["status"] == "completed", snap.get("error")
    updates = _events(client, sid, "update")
    assert updates, "SB3 reported no training updates"
    assert metrics <= set().union(*(set(u) for u in updates)), f"missing {metrics} in {updates[-1]}"
    assert all(np.isfinite(v) for u in updates for k, v in u.items() if k in metrics)
    episodes = [ep for batch in _events(client, sid, "episodes") for ep in batch["episodes"]]
    assert episodes
    evaluations = _events(client, sid, "evaluation")
    assert evaluations and np.isfinite(evaluations[-1]["mean_reward"])  # the stateful LSTM eval and the rest


def test_the_continuous_agents_refuse_manual_control_and_the_brain_view(client: TestClient) -> None:
    if not HAS_BOX2D:
        pytest.skip("Box2D is not installed")
    sid = _create(client, agent="SAC", environment="lunarlander_continuous", agent_params=SMALL_REPLAY, training={**QUICK, "total_timesteps": 20000})
    client.post(f"{BASE}/sessions/{sid}/start")
    assert client.post(f"{BASE}/sessions/{sid}/control", json={"active": True}).status_code == 409
    assert client.post(f"{BASE}/sessions/{sid}/brain", json={"enabled": True}).status_code == 409
    client.post(f"{BASE}/sessions/{sid}/stop")
    _wait(client, sid, {"stopped", "completed", "failed"})


# ------------------------------------------------------------------ environment dynamics reach the simulators


def test_warehouse_grid_size_and_obstacle_count_are_real() -> None:
    _, _, env = _env("warehouse", grid_size=15, num_obstacles=20, obstacle_movement=True)
    cfg = env.unwrapped.config
    assert (cfg.rows, cfg.cols) == (15, 15) and len(cfg.obstacles) == 20
    assert env.observation_space.shape == (6,)


def test_moving_obstacles_move_and_never_trap_or_overlap_the_agent() -> None:
    definition, _, env = _env("warehouse", grid_size=15, num_obstacles=20, obstacle_movement=True, max_episode_steps=300)
    env.reset(seed=3)
    start = [tuple(o) for o in env.unwrapped.config.obstacles]
    seen = {tuple(sorted(start))}
    rng = np.random.default_rng(0)
    for _ in range(200):
        _, _, terminated, truncated, _ = env.step(int(rng.integers(4)))
        cfg = env.unwrapped.config
        cells = [tuple(o) for o in cfg.obstacles]
        assert len(cells) == len(set(cells)) == 20
        assert tuple(env.unwrapped._pos) not in cells and tuple(cfg.goal) not in cells and tuple(cfg.start) not in cells
        seen.add(tuple(sorted(cells)))
        assert definition.frame_state(env, None)["obstacles"] == [list(c) for c in cells]
        if terminated or truncated:
            env.reset()
    assert len(seen) > 10, "obstacles never moved"
    env.reset(seed=3)
    assert [tuple(o) for o in env.unwrapped.config.obstacles] == start  # a reset restores the layout


def test_static_warehouse_obstacles_stay_put_and_frames_omit_them() -> None:
    definition, _, env = _env("warehouse", grid_size=8, num_obstacles=6)
    env.reset(seed=1)
    before = list(env.unwrapped.config.obstacles)
    for _ in range(30):
        env.step(1)
    assert env.unwrapped.config.obstacles == before and "obstacles" not in definition.frame_state(env, None)


def test_impossible_warehouse_settings_are_rejected_up_front(client: TestClient) -> None:
    body = {"agent": "PPO", "environment": "warehouse", "env_params": {"grid_size": 5, "num_obstacles": 30}, "training": QUICK}
    response = client.post(f"{BASE}/sessions", json=body)
    assert response.status_code == 422 and "num_obstacles" in response.text
    for bad in ({"grid_size": 4}, {"grid_size": 21}, {"num_obstacles": 51}, {"obstacle_movement": "yes"}):
        assert client.post(f"{BASE}/sessions", json={**body, "env_params": bad}).status_code == 422


def test_a_15x15_warehouse_with_20_moving_obstacles_runs_end_to_end(client: TestClient) -> None:
    env_params = {"grid_size": 15, "num_obstacles": 20, "obstacle_movement": True}
    sid = _create(client, environment="warehouse", env_params=env_params, training={**QUICK, "total_timesteps": 2000})
    snap = client.get(f"{BASE}/sessions/{sid}").json()
    assert snap["scene"]["rows"] == snap["scene"]["cols"] == 15
    assert len(snap["scene"]["obstacles"]) == 20 and snap["scene"]["moving_obstacles"] is True
    assert snap["config"]["env_params"]["grid_size"] == 15
    client.post(f"{BASE}/sessions/{sid}/start")
    assert _wait(client, sid, {"completed", "failed", "stopped"})["status"] == "completed"


def test_cartpole_gravity_and_pole_length_change_the_physics() -> None:
    _, _, heavy = _env("cartpole", gravity=20.0, pole_length=1.5)
    _, _, light = _env("cartpole", gravity=1.0, pole_length=0.2)
    assert heavy.unwrapped.gravity == 20.0 and heavy.unwrapped.length == 1.5
    for env in (heavy, light):
        env.reset(seed=0)
        env.unwrapped.state = np.array([0.0, 0.0, 0.05, 0.0])
    for _ in range(5):
        heavy.step(0)
        light.step(0)
    assert abs(heavy.unwrapped.state[2] - light.unwrapped.state[2]) > 1e-3


@needs_box2d
def test_lunarlander_gravity_and_wind_reach_the_simulator() -> None:
    _, _, env = _env("lunarlander", gravity=-2.0, wind_power=12.0)
    base = env.unwrapped
    base.reset(seed=0)
    assert base.world.gravity[1] == -2.0 and base.enable_wind is True and base.wind_power == 12.0
    _, _, calm = _env("lunarlander")
    assert calm.unwrapped.world.gravity[1] == -10.0 and calm.unwrapped.enable_wind is False
    fall_slow, fall_fast = [], []
    for sim, bucket in ((env, fall_slow), (calm, fall_fast)):
        sim.reset(seed=0)
        for _ in range(40):
            sim.step(0)
        bucket.append(sim.unwrapped.lander.linearVelocity.y)
    assert fall_slow[0] > fall_fast[0], "weaker gravity must give a slower fall"


@needs_box2d
def test_lunarlander_reports_why_episodes_end_and_frames_carry_real_state() -> None:
    definition, _, env = _env("lunarlander", max_episode_steps=400)
    env.reset(seed=2)
    reasons = set()
    for _ in range(600):
        _, _, terminated, truncated, info = env.step(0)
        if terminated or truncated:
            reasons.add(info["terminal_reason"])
            break
    assert reasons <= {"crashed", "landed", "out_of_bounds", "time_limit"} and reasons
    state = definition.frame_state(env, None)
    assert {"x", "y", "angle", "terrain", "helipad", "left_contact"} <= set(state) and len(state["terrain"]) >= 10


@needs_box2d
def test_bipedalwalker_frames_and_termination_reason() -> None:
    definition, _, env = _env("bipedalwalker", max_episode_steps=300)
    env.reset(seed=0)
    state = definition.frame_state(env, None)
    assert len(state["legs"]) == 4 and len(state["terrain"]) > 20
    for _ in range(400):
        _, _, terminated, truncated, info = env.step(np.zeros(4, dtype=np.float32))
        if terminated or truncated:
            assert info["terminal_reason"] in {"fell", "course_completed", "time_limit"}
            break
    else:
        raise AssertionError("episode never ended")


def test_mountaincar_force_and_gravity_apply_and_the_hill_is_sparse() -> None:
    _, _, strong = _env("mountaincar", force=0.005)
    _, _, weak = _env("mountaincar", force=0.0005)
    assert strong.unwrapped.force == 0.005 and weak.unwrapped.force == 0.0005
    strong.reset(seed=0)
    _, reward, _, _, _ = strong.step(2)
    assert reward == -1.0
