"""Environment wrappers driven by ``RuntimeControls``.

Order of wrapping (outermost last): environment -> reward shaping -> chaos ->
human control. Each wrapper only adds information to ``info`` under namespaced
keys so the session callback can record exactly what happened.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gymnasium as gym
import numpy as np

from .controls import RuntimeControls


class HumanControlEnv(gym.Wrapper):
    """Replaces the agent's action with the human's while manual control is on."""

    def __init__(self, env: gym.Env, controls: RuntimeControls, sticky: bool, abort: Callable[[], bool]) -> None:
        super().__init__(env)
        self._controls = controls
        self._sticky = sticky
        self._abort = abort

    def step(self, action: Any):  # type: ignore[override]
        source = "agent"
        executed = action
        if self._controls.human_active:
            human = self._controls.wait_action(self._sticky, self._abort)
            if human is not None:
                source, executed = "human", human
        env_action = executed
        if source == "human" and isinstance(self.env.action_space, gym.spaces.Discrete):
            env_action = int(executed)  # type: ignore[arg-type]
        obs, reward, terminated, truncated, info = self.env.step(env_action)
        info["action_source"] = source
        if source == "human":
            info["executed_action"] = executed
            self._controls.human_steps += 1
        return obs, reward, terminated, truncated, info


# Per-step base rates; the live intensity (0..1) scales them.
SLIP_RATE = 0.15
IMPULSE_RATE = 0.06
IMPULSE_STRENGTH = 0.35  # cart velocity change at intensity 1 (m/s)


class ChaosEnv(gym.Wrapper):
    """Injects disturbances: actuator slips, sudden physical impulses and sensor noise.

    Random disturbances follow the live chaos configuration; ``trigger_chaos``
    forces a single one on the next step. Every disturbance is reported in
    ``info["chaos"]`` so it can be logged and stored with the step. The agent
    receives the perturbed observation, which is also what gets recorded.
    """

    def __init__(self, env: gym.Env, controls: RuntimeControls, seed: int, noise_scale: tuple[float, ...]) -> None:
        super().__init__(env)
        self._controls = controls
        self._rng = np.random.default_rng(seed + 7919)
        self._noise_scale = np.asarray(noise_scale, dtype=np.float32)

    def _noisy(self, obs: np.ndarray, intensity: float) -> np.ndarray:
        scale = self._noise_scale
        if scale.shape != obs.shape or not scale.any():
            return obs
        return (obs + self._rng.normal(0.0, 1.0, obs.shape).astype(np.float32) * scale * float(intensity)).astype(np.float32)

    def reset(self, **kwargs: Any):  # type: ignore[override]
        obs, info = self.env.reset(**kwargs)
        enabled, intensity, kinds = self._controls.chaos_config()
        if enabled and "sensor_noise" in kinds:
            obs = self._noisy(obs, intensity)
        return obs, info

    def step(self, action: Any):  # type: ignore[override]
        enabled, intensity, kinds = self._controls.chaos_config()
        forced = self._controls.pop_chaos_triggers()
        active = set(kinds) if enabled else set()
        events: list[dict[str, Any]] = []

        space = self.env.action_space
        if isinstance(space, gym.spaces.Discrete) and ("slip" in forced or ("slip" in active and self._rng.random() < SLIP_RATE * intensity)):
            replaced = int(self._rng.integers(0, int(space.n)))
            events.append({"kind": "slip", "intended": int(action), "executed": replaced, "forced": "slip" in forced})
            action = replaced

        state = getattr(self.env.unwrapped, "state", None)
        if state is not None and ("impulse" in forced or ("impulse" in active and self._rng.random() < IMPULSE_RATE * intensity)):
            push = IMPULSE_STRENGTH * max(intensity, 0.3) * (1.0 if self._rng.random() < 0.5 else -1.0)
            nudged = np.array(state, dtype=np.float64)
            nudged[1] += push
            self.env.unwrapped.state = nudged
            events.append({"kind": "impulse", "velocity_change": round(float(push), 4), "forced": "impulse" in forced})

        obs, reward, terminated, truncated, info = self.env.step(action)
        if "sensor_noise" in forced or "sensor_noise" in active:
            level = intensity if "sensor_noise" in active else max(intensity, 0.5)
            obs = self._noisy(obs, level)
            events.append({"kind": "sensor_noise", "level": round(float(level), 3), "forced": "sensor_noise" in forced})
        info["chaos"] = events
        return obs, reward, terminated, truncated, info
