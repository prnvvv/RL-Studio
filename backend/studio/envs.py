"""Studio environment definitions backed by real Gymnasium environments.

Each :class:`EnvDefinition` owns three things that must stay consistent: how the
environment is built, which settings it accepts, and how its live state is
turned into a renderer-neutral frame. The frontend never computes any of this.
"""

from __future__ import annotations

import importlib.util
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
from .wrappers import MovingObstacleEnv, TerminalReason


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
    #: Cross-field check of validated settings; raises ``ValueError`` with a user-facing message.
    check: Callable[[dict[str, Any]], None] | None = None
    #: Whether a human can drive this environment from the keyboard.
    manual: bool = True
    #: Python module this environment needs (for example ``Box2D``); absent means it cannot run.
    requires: str | None = None
    requires_hint: str = ""


def unavailable_reason(definition: EnvDefinition) -> str | None:
    """Why this environment cannot run here, or None when everything it needs is installed."""
    if definition.requires and importlib.util.find_spec(definition.requires) is None:
        return f"{definition.requires} is not installed. {definition.requires_hint}".strip()
    if definition.requires:
        try:
            importlib.import_module(definition.requires)
        except Exception: # noqa: BLE001
            return f"{definition.requires} is not installed. {definition.requires_hint}".strip()
    return None


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

WAREHOUSE_MIN_GRID, WAREHOUSE_MAX_GRID, WAREHOUSE_MAX_OBSTACLES = 5, 20, 50

WAREHOUSE_PARAMS: tuple[ParamSpec, ...] = (
    ParamSpec("grid_size", "Grid size", "int", 6, "Side of the square grid (5x5 up to 20x20).", WAREHOUSE_MIN_GRID, WAREHOUSE_MAX_GRID, 1),
    ParamSpec("num_obstacles", "Obstacles", "int", 4, "Number of obstacle cells (0 to 50). The goal always stays reachable.", 0, WAREHOUSE_MAX_OBSTACLES, 1),
    ParamSpec("obstacle_movement", "Moving obstacles", "bool", False, "Obstacles drift to a free neighbouring cell every few steps instead of staying put."),
    ParamSpec("layout_seed", "Layout seed", "int", 0, "Seed for obstacle placement (and their movement).", 0, 1_000_000, 1),
    ParamSpec("max_episode_steps", "Episode length", "int", 100, "Steps before the episode is truncated.", 10, 1000, 10),
    ParamSpec("goal_reward", "Goal reward", "float", 10.0, "Reward for reaching the goal.", 0.0, 1000.0, 0.5),
    ParamSpec("step_reward", "Step reward", "float", -0.01, "Reward added every step.", -5.0, 5.0, 0.01),
    ParamSpec("collision_penalty", "Collision penalty", "float", 0.5, "Penalty (positive) for hitting a wall or obstacle.", 0.0, 100.0, 0.1),
    ParamSpec("collision_ends_episode", "Collision ends episode", "bool", False, "Terminate the episode on collision."),
)


def build_warehouse_config(params: dict[str, Any]) -> WarehouseConfig:
    """Deterministically build a validated layout; obstacles never block the goal."""
    rows = cols = int(params["grid_size"])
    count = int(params["num_obstacles"])
    start, goal = (0, 0), (rows - 1, cols - 1)
    rng = random.Random(int(params["layout_seed"]))
    free = [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in (start, goal)]
    if count > len(free):
        raise ValueError(f"a {rows}x{cols} grid has room for at most {len(free)} obstacles")
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
    raise ValueError("could not generate a solvable layout for these settings; try fewer obstacles")


def _check_warehouse(params: dict[str, Any]) -> None:
    """Reject impossible combinations up front (not when the first episode is built)."""
    side, count = int(params["grid_size"]), int(params["num_obstacles"])
    cap = int(0.4 * (side * side - 2))
    if count > cap:
        raise ValueError(f"num_obstacles: a {side}x{side} grid fits at most {cap} obstacles and stays solvable")
    build_warehouse_config(params)


def _make_warehouse(params: dict[str, Any], seed: int) -> gym.Env:
    env: gym.Env = Warehouse2DEnv(build_warehouse_config(params))
    if params["obstacle_movement"]:
        env = MovingObstacleEnv(env, int(params["layout_seed"]) + seed)
    return env


def _warehouse_scene(params: dict[str, Any], env: gym.Env) -> dict[str, Any]:
    cfg: WarehouseConfig = env.unwrapped.config
    return {
        "rows": cfg.rows,
        "cols": cfg.cols,
        "start": list(cfg.start),
        "goal": list(cfg.goal),
        "obstacles": [list(o) for o in cfg.obstacles],
        "moving_obstacles": bool(params.get("obstacle_movement", False)),
        "environment_version": cfg.environment_version,
    }


def _warehouse_state(env: gym.Env, terminal_obs: np.ndarray | None) -> dict[str, Any]:
    cfg: WarehouseConfig = env.unwrapped.config
    if terminal_obs is not None:
        row, col = int(terminal_obs[0]), int(terminal_obs[1])
    else:
        row, col = env.unwrapped._pos
    state: dict[str, Any] = {
        "row": int(row),
        "col": int(col),
        "distance_to_goal": abs(row - cfg.goal[0]) + abs(col - cfg.goal[1]),
    }
    if getattr(env.unwrapped, "_studio_moving", False):
        # Obstacles move, so their current cells are part of every frame.
        state["obstacles"] = [list(o) for o in cfg.obstacles]
    return state


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

# --------------------------------------------------------------------------- #
# Shared helpers for environments whose "why did it end" comes from the simulator
# --------------------------------------------------------------------------- #


def _reason_classifier(success_reasons: tuple[str, ...]) -> Callable[..., dict[str, Any]]:
    def classify(params: dict[str, Any], terminal_obs: np.ndarray | None, info: dict[str, Any], terminated: bool) -> dict[str, Any]:
        reason = str(info.get("terminal_reason", "time_limit"))
        return {"success": reason in success_reasons, "reason": reason}

    return classify


def _round(values: Any, digits: int = 3) -> list[float]:
    return [round(float(v), digits) for v in values]


# --------------------------------------------------------------------------- #
# MountainCar
# --------------------------------------------------------------------------- #

MOUNTAIN_CAR_PARAMS: tuple[ParamSpec, ...] = (
    ParamSpec("max_episode_steps", "Episode length", "int", 200, "Steps before the episode is truncated.", 50, 1000, 50),
    ParamSpec("force", "Engine force", "float", 0.001, "Acceleration applied by each push. Lower makes the hill harder.", 0.0005, 0.005, 0.0001),
    ParamSpec("gravity", "Gravity", "float", 0.0025, "Pull of the hill. Higher makes the hill harder.", 0.0005, 0.01, 0.0001),
)


def _mountain_car_reason(base: Any, obs: np.ndarray, terminated: bool, truncated: bool) -> str:
    return "goal_reached" if terminated else "time_limit"


def _make_mountain_car(params: dict[str, Any], seed: int) -> gym.Env:
    env = gym.make("MountainCar-v0", max_episode_steps=int(params["max_episode_steps"]))
    env.unwrapped.force = float(params["force"])
    env.unwrapped.gravity = float(params["gravity"])
    return TerminalReason(env, _mountain_car_reason)


def _mountain_car_scene(params: dict[str, Any], env: gym.Env) -> dict[str, Any]:
    base = env.unwrapped
    return {
        "min_position": float(base.min_position),
        "max_position": float(base.max_position),
        "goal_position": float(base.goal_position),
    }


def _mountain_car_state(env: gym.Env, terminal_obs: np.ndarray | None) -> dict[str, Any]:
    raw = terminal_obs if terminal_obs is not None else env.unwrapped.state
    return {"position": round(float(raw[0]), 4), "velocity": round(float(raw[1]), 5)}


# --------------------------------------------------------------------------- #
# LunarLander (Box2D)
# --------------------------------------------------------------------------- #

BOX2D_HINT = "Install it with: pip install swig \"gymnasium[box2d]\""

LUNAR_LANDER_PARAMS: tuple[ParamSpec, ...] = (
    ParamSpec("max_episode_steps", "Episode length", "int", 1000, "Steps before the episode is truncated.", 100, 2000, 50),
    ParamSpec("gravity", "Gravity", "float", -10.0, "Gravitational acceleration (negative pulls down), -10 to -1.", -10.0, -1.0, 0.5),
    ParamSpec("wind_power", "Wind power", "float", 0.0, "Strength of the sideways wind. 0 turns wind off.", 0.0, 20.0, 0.5),
    ParamSpec("turbulence_power", "Turbulence", "float", 1.5, "Strength of the rotational turbulence that accompanies wind.", 0.0, 2.0, 0.1),
)

LUNAR_WORLD_W = 600 / 30
LUNAR_WORLD_H = 400 / 30


def _lunar_reason(base: Any, obs: np.ndarray, terminated: bool, truncated: bool) -> str:
    if truncated and not terminated:
        return "time_limit"
    if abs(float(obs[0])) >= 1.0:
        return "out_of_bounds"
    if base.game_over:
        return "crashed"
    return "landed" if not base.lander.awake else "crashed"


def _lunar_maker(continuous: bool) -> Callable[[dict[str, Any], int], gym.Env]:
    def make(params: dict[str, Any], seed: int) -> gym.Env:
        wind = float(params["wind_power"])
        env = gym.make(
            "LunarLander-v3",
            continuous=continuous,
            gravity=float(params["gravity"]),
            enable_wind=wind > 0,
            wind_power=wind if wind > 0 else 15.0,
            turbulence_power=float(params["turbulence_power"]),
            max_episode_steps=int(params["max_episode_steps"]),
        )
        return TerminalReason(env, _lunar_reason)

    return make


def _lunar_scene(params: dict[str, Any], env: gym.Env) -> dict[str, Any]:
    return {
        "world_w": LUNAR_WORLD_W,
        "world_h": LUNAR_WORLD_H,
        "continuous": bool(getattr(env.unwrapped, "continuous", False)),
        "gravity": float(params["gravity"]),
        "wind_power": float(params["wind_power"]),
    }


def _lunar_state(env: gym.Env, terminal_obs: np.ndarray | None) -> dict[str, Any]:
    base = env.unwrapped
    polys = base.sky_polys
    terrain = [[round(float(p[0][0]), 3), round(float(p[0][1]), 3)] for p in polys]
    terrain.append([round(float(polys[-1][1][0]), 3), round(float(polys[-1][1][1]), 3)])
    return {
        "x": round(float(base.lander.position.x), 3),
        "y": round(float(base.lander.position.y), 3),
        "angle": round(float(base.lander.angle), 4),
        "vx": round(float(base.lander.linearVelocity.x), 3),
        "vy": round(float(base.lander.linearVelocity.y), 3),
        "left_contact": bool(base.legs[0].ground_contact),
        "right_contact": bool(base.legs[1].ground_contact),
        "helipad": [round(float(base.helipad_x1), 3), round(float(base.helipad_x2), 3), round(float(base.helipad_y), 3)],
        "terrain": terrain,
    }


# --------------------------------------------------------------------------- #
# BipedalWalker (Box2D)
# --------------------------------------------------------------------------- #

BIPEDAL_TERRAIN_STEP = 14 / 30.0
BIPEDAL_TERRAIN_LENGTH = 200
BIPEDAL_TERRAIN_GRASS = 10

BIPEDAL_PARAMS: tuple[ParamSpec, ...] = (
    ParamSpec("max_episode_steps", "Episode length", "int", 1600, "Steps before the episode is truncated.", 200, 2000, 100),
    ParamSpec("hardcore", "Hardcore terrain", "bool", False, "Adds ladders, stumps and pitfalls to the course."),
)


def _bipedal_reason(base: Any, obs: np.ndarray, terminated: bool, truncated: bool) -> str:
    if truncated and not terminated:
        return "time_limit"
    if base.game_over or base.hull.position.x < 0:
        return "fell"
    return "course_completed"


def _make_bipedal(params: dict[str, Any], seed: int) -> gym.Env:
    env = gym.make("BipedalWalker-v3", hardcore=bool(params["hardcore"]), max_episode_steps=int(params["max_episode_steps"]))
    return TerminalReason(env, _bipedal_reason)


def _bipedal_scene(params: dict[str, Any], env: gym.Env) -> dict[str, Any]:
    return {
        "terrain_step": BIPEDAL_TERRAIN_STEP,
        "terrain_length": BIPEDAL_TERRAIN_LENGTH,
        "finish_x": (BIPEDAL_TERRAIN_LENGTH - BIPEDAL_TERRAIN_GRASS) * BIPEDAL_TERRAIN_STEP,
        "hardcore": bool(params["hardcore"]),
    }


def _bipedal_state(env: gym.Env, terminal_obs: np.ndarray | None) -> dict[str, Any]:
    base = env.unwrapped
    first = max(0, int(base.hull.position.x / BIPEDAL_TERRAIN_STEP) - 14)
    last = min(len(base.terrain_x), first + 56)
    return {
        "x": round(float(base.hull.position.x), 3),
        "y": round(float(base.hull.position.y), 3),
        "angle": round(float(base.hull.angle), 4),
        "vx": round(float(base.hull.linearVelocity.x), 3),
        "legs": [[round(float(leg.position.x), 3), round(float(leg.position.y), 3), round(float(leg.angle), 4)] for leg in base.legs],
        "terrain": [[round(float(base.terrain_x[i]), 3), round(float(base.terrain_y[i]), 3)] for i in range(first, last)],
    }


_LUNAR_NOISE = (0.02, 0.02, 0.05, 0.05, 0.02, 0.05, 0.0, 0.0)
_BIPEDAL_NOISE = (0.03,) * 14 + (0.02,) * 10

EXTRA_ENVIRONMENTS: dict[str, EnvDefinition] = {
    "mountaincar": EnvDefinition(
        key="mountaincar",
        name="MountainCar",
        description="Drive an underpowered car up a steep hill. The reward is sparse: -1 every step until the flag.",
        dimension="2D",
        difficulty="Intermediate",
        renderer="mountain_car",
        params=MOUNTAIN_CAR_PARAMS,
        make=_make_mountain_car,
        scene=_mountain_car_scene,
        frame_state=_mountain_car_state,
        classify=_reason_classifier(("goal_reached",)),
        manual=False,
        chaos_kinds=("slip", "sensor_noise"),
        noise_scale=(0.02, 0.005),
    ),
    "lunarlander": EnvDefinition(
        key="lunarlander",
        name="LunarLander",
        description="Land a thruster-driven craft on the pad with discrete engine commands. Physics-based, with optional wind.",
        dimension="2D",
        difficulty="Advanced",
        renderer="lunar_lander",
        params=LUNAR_LANDER_PARAMS,
        make=_lunar_maker(False),
        scene=_lunar_scene,
        frame_state=_lunar_state,
        classify=_reason_classifier(("landed",)),
        manual=False,
        chaos_kinds=("slip", "sensor_noise"),
        noise_scale=_LUNAR_NOISE,
        requires="Box2D",
        requires_hint=BOX2D_HINT,
    ),
    "lunarlander_continuous": EnvDefinition(
        key="lunarlander_continuous",
        name="LunarLander (continuous)",
        description="The same lander with continuous throttle control: a Box action space for SAC, TD3 and PPO.",
        dimension="2D",
        difficulty="Advanced",
        renderer="lunar_lander",
        params=LUNAR_LANDER_PARAMS,
        make=_lunar_maker(True),
        scene=_lunar_scene,
        frame_state=_lunar_state,
        classify=_reason_classifier(("landed",)),
        manual=False,
        chaos_kinds=("sensor_noise",),
        noise_scale=_LUNAR_NOISE,
        requires="Box2D",
        requires_hint=BOX2D_HINT,
    ),
    "bipedalwalker": EnvDefinition(
        key="bipedalwalker",
        name="BipedalWalker",
        description="Teach a two-legged robot to walk across uneven terrain with continuous joint torques.",
        dimension="2D",
        difficulty="Advanced",
        renderer="bipedal_walker",
        params=BIPEDAL_PARAMS,
        make=_make_bipedal,
        scene=_bipedal_scene,
        frame_state=_bipedal_state,
        classify=_reason_classifier(("course_completed",)),
        manual=False,
        chaos_kinds=("sensor_noise",),
        noise_scale=_BIPEDAL_NOISE,
        requires="Box2D",
        requires_hint=BOX2D_HINT,
    ),
}

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
        check=_check_warehouse,
    ),
    **EXTRA_ENVIRONMENTS,
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
