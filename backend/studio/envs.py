"""Studio environment definitions backed by real Gymnasium environments.

Each :class:`EnvDefinition` owns three things that must stay consistent: how the
environment is built, which settings it accepts, and how its live state is
turned into a renderer-neutral frame. The frontend never computes any of this.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import gymnasium as gym
import numpy as np

from backend.environments.config import WarehouseConfig
from backend.environments.warehouse_env import Warehouse2DEnv

from .params import ParamSpec


@dataclass(frozen=True)
class EnvDefinition:
    key: str
    name: str
    description: str
    dimension: str  # "2D" | "3D" (how the viewport presents it)
    difficulty: str
    renderer: str  # frontend renderer registry key
    params: tuple[ParamSpec, ...]
    make: Callable[[dict[str, Any], int], gym.Env]
    scene: Callable[[dict[str, Any], gym.Env], dict[str, Any]]
    frame_state: Callable[[gym.Env, np.ndarray | None], dict[str, Any]]
    classify: Callable[[dict[str, Any], np.ndarray | None, dict[str, Any], bool], dict[str, Any]]
    disturbances: bool = False
    #: Keep applying the last manual action until a new one arrives (balancing tasks).
    human_sticky: bool = False
    #: Disturbances this environment can receive in chaos mode.
    chaos_kinds: tuple[str, ...] = ()
    #: Per-observation-dimension noise scale at chaos intensity 1.
    noise_scale: tuple[float, ...] = ()


# --------------------------------------------------------------------------- #
# CartPole
# --------------------------------------------------------------------------- #

CARTPOLE_X_LIMIT = 2.4
CARTPOLE_THETA_LIMIT = 12 * 2 * math.pi / 360


class WindDisturbance(gym.Wrapper):
    """Randomly nudges the cart velocity before a step (a real disturbance)."""

    def __init__(self, env: gym.Env, probability: float, strength: float, seed: int) -> None:
        super().__init__(env)
        self._probability = probability
        self._strength = strength
        self._rng = np.random.default_rng(seed)

    def step(self, action: Any):  # type: ignore[override]
        disturbed = False
        state = getattr(self.env.unwrapped, "state", None)
        if state is not None and self._probability > 0 and self._rng.random() < self._probability:
            nudged = np.array(state, dtype=np.float64)
            nudged[1] += self._strength * (1.0 if self._rng.random() < 0.5 else -1.0)
            self.env.unwrapped.state = nudged
            disturbed = True
        obs, reward, terminated, truncated, info = self.env.step(action)
        info["disturbance"] = disturbed
        return obs, reward, terminated, truncated, info


CARTPOLE_PARAMS: tuple[ParamSpec, ...] = (
    ParamSpec("max_episode_steps", "Episode length", "int", 500, "Steps before the episode is truncated.", 50, 2000, 50),
    ParamSpec("gravity", "Gravity", "float", 9.8, "Gravitational acceleration (m/s²).", 1.0, 20.0, 0.1),
    ParamSpec("pole_length", "Pole half-length", "float", 0.5, "Half the pole length (m).", 0.2, 1.5, 0.05),
    ParamSpec("force_mag", "Push force", "float", 10.0, "Force applied by each action (N).", 2.0, 30.0, 0.5),
    ParamSpec("wind_probability", "Wind probability", "float", 0.0, "Chance per step of a sideways velocity impulse.", 0.0, 0.5, 0.01),
    ParamSpec("wind_strength", "Wind strength", "float", 0.3, "Velocity impulse applied by the wind (m/s).", 0.05, 2.0, 0.05),
)


def _make_cartpole(params: dict[str, Any], seed: int) -> gym.Env:
    env = gym.make("CartPole-v1", max_episode_steps=int(params["max_episode_steps"]))
    base = env.unwrapped
    base.gravity = float(params["gravity"])
    base.length = float(params["pole_length"])
    base.force_mag = float(params["force_mag"])
    base.polemass_length = base.masspole * base.length
    if params["wind_probability"] > 0:
        env = WindDisturbance(env, float(params["wind_probability"]), float(params["wind_strength"]), seed)
    return env


def _cartpole_scene(params: dict[str, Any], env: gym.Env) -> dict[str, Any]:
    return {
        "x_limit": CARTPOLE_X_LIMIT,
        "theta_limit": CARTPOLE_THETA_LIMIT,
        "pole_length": 2.0 * float(params["pole_length"]),
    }


def _cartpole_state(env: gym.Env, terminal_obs: np.ndarray | None) -> dict[str, Any]:
    raw = terminal_obs if terminal_obs is not None else env.unwrapped.state
    x, x_dot, theta, theta_dot = (float(v) for v in raw[:4])
    return {"x": x, "x_dot": x_dot, "theta": theta, "theta_dot": theta_dot}


def _cartpole_classify(
    params: dict[str, Any], terminal_obs: np.ndarray | None, info: dict[str, Any], terminated: bool
) -> dict[str, Any]:
    if not terminated:
        return {"success": True, "reason": "time_limit_reached"}
    if terminal_obs is not None and abs(float(terminal_obs[0])) > CARTPOLE_X_LIMIT:
        return {"success": False, "reason": "cart_out_of_bounds"}
    return {"success": False, "reason": "pole_fell"}


# --------------------------------------------------------------------------- #
# Warehouse navigation
# --------------------------------------------------------------------------- #

_WAREHOUSE_LAYOUTS = {"easy": (6, 6, 4), "medium": (8, 8, 10), "hard": (10, 10, 18)}

WAREHOUSE_PARAMS: tuple[ParamSpec, ...] = (
    ParamSpec("difficulty", "Difficulty", "choice", "easy", "Grid size and obstacle count.", options=("easy", "medium", "hard")),
    ParamSpec("layout_seed", "Layout seed", "int", 0, "Seed for obstacle placement.", 0, 1_000_000, 1),
    ParamSpec("max_episode_steps", "Episode length", "int", 100, "Steps before the episode is truncated.", 10, 1000, 10),
    ParamSpec("goal_reward", "Goal reward", "float", 10.0, "Reward for reaching the goal.", 0.0, 1000.0, 0.5),
    ParamSpec("step_reward", "Step reward", "float", -0.01, "Reward added every step.", -5.0, 5.0, 0.01),
    ParamSpec("collision_penalty", "Collision penalty", "float", 0.5, "Penalty (positive) for hitting a wall or obstacle.", 0.0, 100.0, 0.1),
    ParamSpec("collision_ends_episode", "Collision ends episode", "bool", False, "Terminate the episode on collision."),
)


def build_warehouse_config(params: dict[str, Any]) -> WarehouseConfig:
    """Deterministically build a validated layout; obstacles never block the goal."""
    rows, cols, count = _WAREHOUSE_LAYOUTS[params["difficulty"]]
    start, goal = (0, 0), (rows - 1, cols - 1)
    rng = random.Random(int(params["layout_seed"]))
    free = [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in (start, goal)]
    for _ in range(200):
        obstacles = sorted(rng.sample(free, count))
        try:
            return WarehouseConfig(
                rows=rows,
                cols=cols,
                start=start,
                goal=goal,
                obstacles=obstacles,
                max_episode_steps=int(params["max_episode_steps"]),
                goal_reward=float(params["goal_reward"]),
                step_reward=float(params["step_reward"]),
                collision_penalty=float(params["collision_penalty"]),
                collision_reward=bool(params["collision_ends_episode"]),
            )
        except ValueError:
            continue
    raise ValueError("could not generate a solvable layout for these settings")


def _make_warehouse(params: dict[str, Any], seed: int) -> gym.Env:
    return Warehouse2DEnv(build_warehouse_config(params))


def _warehouse_scene(params: dict[str, Any], env: gym.Env) -> dict[str, Any]:
    cfg: WarehouseConfig = env.unwrapped.config
    return {
        "rows": cfg.rows,
        "cols": cfg.cols,
        "start": list(cfg.start),
        "goal": list(cfg.goal),
        "obstacles": [list(o) for o in cfg.obstacles],
        "environment_version": cfg.environment_version,
    }


def _warehouse_state(env: gym.Env, terminal_obs: np.ndarray | None) -> dict[str, Any]:
    cfg: WarehouseConfig = env.unwrapped.config
    if terminal_obs is not None:
        row, col = int(terminal_obs[0]), int(terminal_obs[1])
    else:
        row, col = env.unwrapped._pos
    return {
        "row": int(row),
        "col": int(col),
        "distance_to_goal": abs(row - cfg.goal[0]) + abs(col - cfg.goal[1]),
    }


def _warehouse_classify(
    params: dict[str, Any], terminal_obs: np.ndarray | None, info: dict[str, Any], terminated: bool
) -> dict[str, Any]:
    pos = info.get("position")
    goal = info.get("goal")
    if pos is not None and goal is not None and tuple(pos) == tuple(goal):
        return {"success": True, "reason": "goal_reached"}
    if terminated:
        return {"success": False, "reason": "collision"}
    return {"success": False, "reason": "time_limit"}


#: Sensor noise perturbs only the agent's own position, never the goal or the layout counts.
WAREHOUSE_CHAOS_KINDS = ("slip", "sensor_noise")
WAREHOUSE_NOISE_SCALE = (0.6, 0.6, 0.0, 0.0, 0.0, 0.0)

ENVIRONMENTS: dict[str, EnvDefinition] = {
    "cartpole": EnvDefinition(
        key="cartpole",
        name="CartPole Balancing",
        description="Balance a pole on a moving cart by pushing it left or right. Optional wind disturbance.",
        dimension="3D",
        difficulty="Beginner",
        renderer="cartpole",
        params=CARTPOLE_PARAMS,
        make=_make_cartpole,
        scene=_cartpole_scene,
        frame_state=_cartpole_state,
        classify=_cartpole_classify,
        disturbances=True,
        human_sticky=True,
        chaos_kinds=("impulse", "sensor_noise", "slip"),
        noise_scale=(0.25, 0.5, 0.05, 0.5),
    ),
    "warehouse": EnvDefinition(
        key="warehouse",
        name="Warehouse Navigation",
        description="Navigate a grid warehouse around obstacles to a goal. Rendered as a 3D maze.",
        dimension="3D",
        difficulty="Intermediate",
        renderer="grid_maze",
        params=WAREHOUSE_PARAMS,
        make=_make_warehouse,
        scene=_warehouse_scene,
        frame_state=_warehouse_state,
        classify=_warehouse_classify,
        chaos_kinds=WAREHOUSE_CHAOS_KINDS,
        noise_scale=WAREHOUSE_NOISE_SCALE,
    ),
}


def describe_space(space: gym.Space) -> dict[str, Any]:
    if isinstance(space, gym.spaces.Discrete):
        return {"type": "discrete", "n": int(space.n)}
    if isinstance(space, gym.spaces.Box):
        return {
            "type": "box",
            "shape": [int(s) for s in space.shape],
            "low": [None if not np.isfinite(v) else round(float(v), 4) for v in space.low.flat],
            "high": [None if not np.isfinite(v) else round(float(v), 4) for v in space.high.flat],
        }
    return {"type": type(space).__name__}
