"""Environment wrappers driven by ``RuntimeControls``.

Order of wrapping (outermost last): environment -> reward shaping -> chaos ->
human control. Each wrapper only adds information to ``info`` under namespaced
keys so the session callback can record exactly what happened.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gymnasium as gym

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
