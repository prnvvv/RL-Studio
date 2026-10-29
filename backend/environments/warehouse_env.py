"""Gymnasium 2D warehouse-navigation environment (Person 2)."""

from __future__ import annotations

from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .config import Coord, WarehouseConfig


class Warehouse2DEnv(gym.Env):
    metadata: ClassVar[dict[str, Any]] = {
        "render_modes": ["human", "rgb_array"],
        "render_fps": 4,
    }

    def __init__(self, config: WarehouseConfig | dict, render_mode: str | None = None):
        super().__init__()
        if isinstance(config, dict):
            config = WarehouseConfig.model_validate(config)
        self.config = config
        self.render_mode = render_mode

        self.action_space = spaces.Discrete(4)
        self.observation_space = spaces.Box(
            low=np.array([0, 0, 0, 0, 0.0, 0.0], dtype=np.float32),
            high=np.array(
                [
                    float(max(1, config.rows - 1)),
                    float(max(1, config.cols - 1)),
                    float(max(1, config.rows - 1)),
                    float(max(1, config.cols - 1)),
                    float(config.rows + config.cols),
                    float(len(config.obstacles)),
                ],
                dtype=np.float32,
            ),
            dtype=np.float32,
        )

        self._pos: Coord = config.start
        self._steps = 0

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        super().reset(seed=seed)
        self._pos = tuple(self.config.start)
        self._steps = 0
        obs = self._get_obs()
        info = self._get_info()
        return obs, info

    def _get_obs(self) -> np.ndarray:
        r, c = self._pos
        gr, gc = self.config.goal
        dist = float(abs(r - gr) + abs(c - gc))
        return np.array(
            [float(r), float(c), float(gr), float(gc), dist, float(len(self.config.obstacles))],
            dtype=np.float32,
        )

    def _get_info(self) -> dict[str, Any]:
        return {
            "position": (int(self._pos[0]), int(self._pos[1])),
            "goal": tuple(self.config.goal),
            "steps": int(self._steps),
            "environment_id": self.config.environment_id,
            "environment_version": self.config.environment_version,
        }

    def step(self, action: int):
        self._steps += 1
        dr, dc = [(-1, 0), (1, 0), (0, -1), (0, 1)][int(action)]
        nr, nc = self._pos[0] + dr, self._pos[1] + dc
        new_pos = (nr, nc)

        reward = float(self.config.step_reward)
        terminated = False
        truncated = False
        collision = False

        if nr < 0 or nc < 0 or nr >= self.config.rows or nc >= self.config.cols or new_pos in self.config.normalized_obstacles():
            collision = True
            new_pos = self._pos

        if collision:
            reward += float(-abs(self.config.collision_penalty))
            if self.config.collision_reward:
                terminated = True
        else:
            self._pos = new_pos

        if self._pos == self.config.goal:
            reward += float(self.config.goal_reward)
            terminated = True

        if not terminated and self._steps >= self.config.max_episode_steps:
            truncated = True

        obs = self._get_obs()
        info = self._get_info()
        info["collision"] = bool(collision)
        return obs, float(reward), bool(terminated), bool(truncated), info
