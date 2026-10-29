"""Raw episode metrics vs rolling aggregates with explicit windows/denominators."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class EpisodeMetrics:
    episode_id: str
    run_id: str
    rewards: list[float] = field(default_factory=list)
    lengths: list[int] = field(default_factory=list)
    collisions: int = 0
    successes: int = 0

    def add_step(self, reward: float, collision: bool = False):
        self.rewards.append(float(reward))
        if collision:
            self.collisions += 1

    def end(self, success: bool = False):
        self.lengths.append(len(self.rewards))
        if success:
            self.successes += 1

    def summary(self) -> Dict[str, Any]:
        total_r = sum(self.rewards)
        return {
            "episode_id": self.episode_id,
            "run_id": self.run_id,
            "total_reward": total_r,
            "length": len(self.rewards),
            "collisions": self.collisions,
            "success": bool(self.successes > 0),
        }


class RollingMetrics:
    def __init__(self, window: int = 100):
        self.window = int(window)
        self._rewards = deque(maxlen=self.window)
        self._lengths = deque(maxlen=self.window)
        self._collisions = deque(maxlen=self.window)
        self._successes = deque(maxlen=self.window)

    def add_episode(self, total_reward: float, length: int, collisions: int, success: bool):
        self._rewards.append(float(total_reward))
        self._lengths.append(int(length))
        self._collisions.append(int(collisions))
        self._successes.append(1.0 if success else 0.0)

    def aggregate(self) -> Dict[str, Any]:
        if not self._rewards:
            return {
                "window": self.window,
                "count": 0,
                "mean_reward": 0.0,
                "mean_length": 0.0,
                "collision_rate": 0.0,
                "success_rate": 0.0,
                "denom": "episodes",
            }
        n = len(self._rewards)
        return {
            "window": self.window,
            "count": n,
            "mean_reward": sum(self._rewards) / n,
            "mean_length": sum(self._lengths) / n,
            "collision_rate": sum(self._collisions) / sum(self._lengths) if sum(self._lengths) > 0 else 0.0,
            "success_rate": sum(self._successes) / n,
            "denom": "episodes/steps",
        }
