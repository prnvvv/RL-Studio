"""Allow-listed faults: reward scaling, observation corruption, invalid termination."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class FaultType(str, Enum):
    REWARD_SCALING = "reward_scaling"
    OBSERVATION_CORRUPTION = "observation_corruption"
    INVALID_TERMINATION = "invalid_termination"


@dataclass
class FaultConfig:
    fault_type: FaultType
    enabled: bool = True
    trigger_step: int = 0  # trigger at or after this global step (exact boundary)
    trigger_episode: int = 0
    scale: float = 10.0  # for reward scaling
    noise_scale: float = 1.0  # for obs corruption
    seed: int = 12345


class FaultInjector:
    def __init__(self, config: FaultConfig):
        self.config = config
        self.rng = np.random.RandomState(config.seed)
        self._applied = False

    def should_trigger(self, step: int, episode: int) -> bool:
        if not self.config.enabled:
            return False
        if self._applied:
            return False  # no cross-run leakage within instance
        if episode < self.config.trigger_episode:
            return False
        if step < self.config.trigger_step:
            return False
        return True

    def apply_reward_scaling(self, reward: float, step: int, episode: int) -> float:
        if not self.should_trigger(step, episode):
            return float(reward)
        self._applied = True
        return float(reward) * float(self.config.scale)

    def apply_observation_corruption(self, obs: np.ndarray, step: int, episode: int) -> np.ndarray:
        if not self.should_trigger(step, episode):
            return obs
        self._applied = True
        obs = obs.copy()
        noise = self.rng.normal(0.0, self.config.noise_scale, size=obs.shape).astype(obs.dtype)
        return obs + noise

    def apply_termination(self, terminated: bool, step: int, episode: int) -> bool:
        if not self.should_trigger(step, episode):
            return bool(terminated)
        self._applied = True
        # Force invalid termination (early) as specified
        return True
