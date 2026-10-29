"""PPO wrapper with validated hyperparameters, seed discipline, and run lifecycle."""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

import numpy as np

try:
    import torch
except Exception:  # pragma: no cover
    torch = None  # type: ignore

from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from backend.environments.config import WarehouseConfig
from backend.environments.fingerprints import agent_fingerprint, config_fingerprint, run_fingerprint


class RunStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    STOP_REQUESTED = "stop_requested"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RunState:
    run_id: str
    status: RunStatus
    stop_requested: bool = False


@dataclass
class RunConfig:
    run_id: str
    config: WarehouseConfig | dict
    seed: int = 0
    total_timesteps: int = 10_000
    policy: str = "MlpPolicy"
    learning_rate: float = 3e-4
    n_steps: int = 2048
    batch_size: int = 64
    n_epochs: int = 10
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_range: float = 0.2
    ent_coef: float = 0.0
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    verbose: int = 1


class PPOTrainer:
    def __init__(self, run_config: RunConfig):
        self.run_config = run_config
        self.state = RunState(run_id=run_config.run_id, status=RunStatus.CREATED)
        self.model: Optional[PPO] = None
        self.env = None
        self._stop_requested = False

        if isinstance(run_config.config, dict):
            self.config = WarehouseConfig.model_validate(run_config.config)
        else:
            self.config = run_config.config

    def set_seeds(self, seed: int):
        random.seed(seed)
        np.random.seed(seed)
        try:
            if torch is not None:
                torch.manual_seed(seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(seed)
        except Exception:
            pass
        os.environ["PYTHONHASHSEED"] = str(seed)

    def _make_env(self):
        from backend.environments.warehouse_env import Warehouse2DEnv

        def _init():
            env = Warehouse2DEnv(self.config)
            env = Monitor(env)
            return env

        return DummyVecEnv([_init])

    def fingerprints(self) -> Dict[str, str]:
        cfg_fp = config_fingerprint(self.config)
        agent_fp = agent_fingerprint(
            "PPO",
            {
                "policy": self.run_config.policy,
                "learning_rate": self.run_config.learning_rate,
                "n_steps": self.run_config.n_steps,
                "batch_size": self.run_config.batch_size,
                "n_epochs": self.run_config.n_epochs,
                "gamma": self.run_config.gamma,
                "gae_lambda": self.run_config.gae_lambda,
                "clip_range": self.run_config.clip_range,
                "ent_coef": self.run_config.ent_coef,
                "vf_coef": self.run_config.vf_coef,
                "max_grad_norm": self.run_config.max_grad_norm,
            },
        )
        run_fp = run_fingerprint(config_fingerprint=cfg_fp, agent_fingerprint=agent_fp, seed=self.run_config.seed)
        return {"config_fingerprint": cfg_fp, "agent_fingerprint": agent_fp, "run_fingerprint": run_fp}

    def start(self, callbacks=None):
        if self.state.status in (RunStatus.RUNNING, RunStatus.STARTING):
            return self
        self.set_seeds(self.run_config.seed)
        self.state.status = RunStatus.STARTING
        self.env = self._make_env()
        self.model = PPO(
            self.run_config.policy,
            self.env,
            learning_rate=self.run_config.learning_rate,
            n_steps=self.run_config.n_steps,
            batch_size=self.run_config.batch_size,
            n_epochs=self.run_config.n_epochs,
            gamma=self.run_config.gamma,
            gae_lambda=self.run_config.gae_lambda,
            clip_range=self.run_config.clip_range,
            ent_coef=self.run_config.ent_coef,
            vf_coef=self.run_config.vf_coef,
            max_grad_norm=self.run_config.max_grad_norm,
            verbose=self.run_config.verbose,
            seed=self.run_config.seed,
        )
        self.state.status = RunStatus.RUNNING
        try:
            self.model.learn(total_timesteps=self.run_config.total_timesteps, callback=callbacks)
            if self._stop_requested:
                self.state.status = RunStatus.STOPPED
            else:
                self.state.status = RunStatus.COMPLETED
        except Exception:
            self.state.status = RunStatus.FAILED
            raise
        return self

    def stop(self, idempotent: bool = True):
        if self.state.status in (RunStatus.STOPPED, RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
            if idempotent:
                return self
        self._stop_requested = True
        self.state.stop_requested = True
        self.state.status = RunStatus.STOP_REQUESTED
        try:
            if self.model is not None:
                self.model.save("stop_request")
        except Exception:
            pass
        return self
