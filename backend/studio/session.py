"""A single training session: lifecycle, real SB3 training thread, live telemetry.

Lifecycle (``Status``)::

    initialized -> running <-> paused
    running/paused -> stopping -> stopped
    running -> completed | failed
    stopped | completed | failed | initialized -> (reset) -> initialized

Repeating a command that has already taken effect is an idempotent no-op; a
command that is invalid for the current state raises ``ConflictError``.
Pause and stop are *requests* acknowledged by the training thread at the next
environment step, so the API reports them as ``pending_command`` until then.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.logger import KVWriter, Logger
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from backend.database.exceptions import ConflictError, ValidationError

from .catalog import AGENTS, NET_ARCHES, TRAINING_PARAMS, sb3_class
from .envs import ENVIRONMENTS, EnvDefinition
from .hub import SessionHub
from .params import validate_params

logger = logging.getLogger(__name__)

BASE_STEPS_PER_SECOND = 30.0  # 1x playback speed
FRAME_INTERVAL_S = 1.0 / 30.0
PROGRESS_INTERVAL_S = 0.5
EPISODE_FLUSH_INTERVAL_S = 0.15
MAX_EPISODES_KEPT = 5000
MAX_UPDATES_KEPT = 2000
RECENT_WINDOW = 20


class Status(str, Enum):
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


ACTIVE = {Status.RUNNING, Status.PAUSED, Status.STOPPING}
RESETTABLE = {Status.INITIALIZED, Status.STOPPED, Status.COMPLETED, Status.FAILED}

_UPDATE_KEYS = {
    "train/policy_gradient_loss": "policy_loss",
    "train/policy_loss": "policy_loss",
    "train/value_loss": "value_loss",
    "train/approx_kl": "approx_kl",
    "train/explained_variance": "explained_variance",
    "train/clip_fraction": "clip_fraction",
    "train/loss": "loss",
    "rollout/exploration_rate": "exploration_rate",
}


def data_dir() -> Path:
    override = os.environ.get("STUDIO_DATA_DIR")
    base = Path(override) if override else Path(__file__).resolve().parents[2] / "var" / "studio"
    return base


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise a session request; raises ``ValidationError``."""
    agent_key = raw.get("agent")
    env_key = raw.get("environment")
    errors: list[dict[str, str]] = []
    if agent_key not in AGENTS:
        errors.append({"field": "agent", "message": f"unknown agent {agent_key!r}"})
    if env_key not in ENVIRONMENTS:
        errors.append({"field": "environment", "message": f"unknown environment {env_key!r}"})
    if errors:
        raise ValidationError("Invalid configuration", details={"errors": errors})

    agent = AGENTS[agent_key]
    definition = ENVIRONMENTS[env_key]
    probe = definition.make(validate_params(definition.params, {}, scope="env_params"), 0)
    try:
        action_type = "discrete" if hasattr(probe.action_space, "n") else "box"
    finally:
        probe.close()
    if action_type not in agent.action_spaces:
        raise ValidationError(
            "Incompatible agent and environment",
            details={"errors": [{"field": "agent", "message": f"{agent_key} does not support {action_type} actions"}]},
        )

    agent_params = validate_params(agent.params, raw.get("agent_params"), scope="agent_params")
    env_params = validate_params(definition.params, raw.get("env_params"), scope="env_params")
    training = validate_params(TRAINING_PARAMS, raw.get("training"), scope="training")

    cross: list[dict[str, str]] = []
    if "batch_size" in agent_params and agent_key == "PPO" and agent_params["batch_size"] > agent_params["n_steps"]:
        cross.append({"field": "agent_params.batch_size", "message": "must not exceed steps per update"})
    if agent_key == "DQN" and agent_params["learning_starts"] >= training["total_timesteps"]:
        cross.append({"field": "agent_params.learning_starts", "message": "must be below total timesteps"})
    if agent_key == "DQN" and agent_params["buffer_size"] < agent_params["batch_size"]:
        cross.append({"field": "agent_params.buffer_size", "message": "must be at least the batch size"})
    if cross:
        raise ValidationError("Invalid configuration", details={"errors": cross})

    return {
        "agent": agent_key,
        "environment": env_key,
        "agent_params": agent_params,
        "env_params": env_params,
        "training": training,
    }


class _HubWriter(KVWriter):
    """SB3 logger sink that forwards real algorithm statistics to the session."""

    def __init__(self, session: TrainingSession) -> None:
        self._session = session

    def write(self, key_values: dict[str, Any], key_excluded: dict[str, Any], step: int = 0) -> None:
        self._session._on_algorithm_stats(key_values, step)

    def close(self) -> None:  # pragma: no cover - nothing to release
        pass


class _StudioCallback(BaseCallback):
    def __init__(self, session: TrainingSession, definition: EnvDefinition) -> None:
        super().__init__(0)
        self.s = session
        self.definition = definition
        self._episode_reward = 0.0
        self._episode_steps = 0
        self._episode_collisions = 0
        self._episode_disturbances = 0
        self._last_frame = 0.0
        self._next_t = time.monotonic()
        self._last_checkpoint = 0
        self._last_eval = 0

    def _on_step(self) -> bool:
        s = self.s
        if s._stop.is_set():
            return False
        if s._pause.is_set():
            s._block_while_paused()
            self._next_t = time.monotonic()
            if s._stop.is_set():
                return False

        env = self.training_env.envs[0]
        action = self.locals["actions"][0]
        reward = float(self.locals["rewards"][0])
        done = bool(self.locals["dones"][0])
        info = self.locals["infos"][0]
        action_value: Any = int(action) if getattr(action, "ndim", 1) == 0 else [float(a) for a in action]

        collision = bool(info.get("collision", False))
        disturbed = bool(info.get("disturbance", False))
        self._episode_reward += reward
        self._episode_steps += 1
        self._episode_collisions += int(collision)
        self._episode_disturbances += int(disturbed)
        timestep = int(self.num_timesteps)

        terminal_obs = info.get("terminal_observation") if done else None
        outcome: dict[str, Any] | None = None
        if done:
            truncated = bool(info.get("TimeLimit.truncated", False))
            outcome = self.definition.classify(s.config["env_params"], terminal_obs, info, not truncated)
        now = time.monotonic()
        if done or now - self._last_frame >= FRAME_INTERVAL_S:
            self._last_frame = now
            payload: dict[str, Any] = {
                "timestep": timestep,
                "episode": s._episode_count + 1,
                "episode_step": self._episode_steps,
                "action": action_value,
                "reward": reward,
                "episode_reward": self._episode_reward,
                "collision": collision,
                "disturbance": disturbed,
                "done": done,
                "state": self.definition.frame_state(env, terminal_obs),
            }
            if outcome is not None:
                payload["outcome"] = outcome
            s._last_state = payload["state"]
            s.hub.set_frame(payload)

        if outcome is not None:
            s._record_episode(
                reward=self._episode_reward,
                length=self._episode_steps,
                outcome=outcome,
                collisions=self._episode_collisions,
                disturbances=self._episode_disturbances,
                timestep=timestep,
            )
            self._episode_reward = 0.0
            self._episode_steps = 0
            self._episode_collisions = 0
            self._episode_disturbances = 0

        s._maybe_progress(timestep, force=False)
        training = s.config["training"]
        if training["checkpoint_every"] and timestep - self._last_checkpoint >= training["checkpoint_every"]:
            self._last_checkpoint = timestep
            s._save_checkpoint(self.model, timestep, reason="interval")
        if training["eval_every"] and timestep - self._last_eval >= training["eval_every"]:
            self._last_eval = timestep
            s._evaluate(self.model, timestep)

        self._pace()
        return True

    def _pace(self) -> None:
        speed = self.s.speed
        if speed <= 0:
            self._next_t = time.monotonic()
            return
        self._next_t += 1.0 / (BASE_STEPS_PER_SECOND * speed)
        delay = self._next_t - time.monotonic()
        if delay > 0:
            time.sleep(min(delay, 0.25))
        elif delay < -0.5:
            self._next_t = time.monotonic()


class TrainingSession:
    def __init__(self, session_id: str, config: dict[str, Any], name: str | None = None) -> None:
        self.session_id = session_id
        self.name = name or f"{config['agent']} on {config['environment']}"
        self.config = config
        self.definition = ENVIRONMENTS[config["environment"]]
        self.hub = SessionHub(session_id)
        self.created_at = _now()
        self.started_at: str | None = None
        self.finished_at: str | None = None
        self.error: str | None = None
        self.run_index = 1
        self.speed = float(config["training"]["simulation_speed"])

        self._lock = threading.RLock()
        self._status = Status.INITIALIZED
        self._pending: str | None = None
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._resume = threading.Event()
        self._thread: threading.Thread | None = None
        self._model: Any = None
        self._scene: dict[str, Any] = {}
        self._reset_metrics()
        self._build_preview()
        self.log("INFO", "TRAINING", "Session initialized", {"config": self._config_summary()})

    # ------------------------------------------------------------------ state

    @property
    def run_id(self) -> str:
        return f"{self.session_id}_r{self.run_index}"

    @property
    def status(self) -> Status:
        return self._status

    def _config_summary(self) -> dict[str, Any]:
        c = self.config
        return {"agent": c["agent"], "environment": c["environment"], "seed": c["training"]["seed"]}

    def _reset_metrics(self) -> None:
        self._episodes: deque[dict[str, Any]] = deque(maxlen=MAX_EPISODES_KEPT)
        self._updates: deque[dict[str, Any]] = deque(maxlen=MAX_UPDATES_KEPT)
        self._evals: list[dict[str, Any]] = []
        self._checkpoints: list[dict[str, Any]] = []
        self._unsent: list[dict[str, Any]] = []
        self._episode_count = 0
        self._successes: deque[int] = deque(maxlen=50)
        self._recent: deque[float] = deque(maxlen=RECENT_WINDOW)
        self._reward_sum = 0.0
        self._best_reward: float | None = None
        self._collisions = 0
        self._disturbances = 0
        self._timestep = 0
        self._started_monotonic: float | None = None
        self._ended_monotonic: float | None = None
        self._paused_accum = 0.0
        self._last_flush = 0.0
        self._last_progress = 0.0
        self._last_termination: str | None = None
        self._paused_since: float | None = None
        self._last_state: dict[str, float] = {}

    def _build_preview(self) -> None:
        """Create the environment once so the viewport shows the real scene."""
        env = self.definition.make(self.config["env_params"], self.config["training"]["seed"])
        try:
            env.reset(seed=self.config["training"]["seed"])
            self._scene = self.definition.scene(self.config["env_params"], env)
            self._scene["action_space"] = "discrete" if hasattr(env.action_space, "n") else "box"
            self.hub.set_frame(
                {
                    "timestep": 0,
                    "episode": 0,
                    "episode_step": 0,
                    "action": None,
                    "reward": 0.0,
                    "episode_reward": 0.0,
                    "collision": False,
                    "disturbance": False,
                    "done": False,
                    "initial": True,
                    "state": self.definition.frame_state(env, None),
                }
            )
        finally:
            env.close()

    def _set_status(self, status: Status, **extra: Any) -> None:
        with self._lock:
            previous = self._status
            self._status = status
            self._pending = None
        self.hub.publish("lifecycle", {"status": status.value, "previous": previous.value, "run_id": self.run_id, **extra})

    # --------------------------------------------------------------- commands

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._status != Status.INITIALIZED:
                raise ConflictError(
                    f"Cannot start a session that is {self._status.value}",
                    details={"status": self._status.value},
                )
            self._stop.clear()
            self._pause.clear()
            self._resume.set()
            self.started_at = _now()
            self._started_monotonic = time.monotonic()
            self._thread = threading.Thread(target=self._run, name=f"studio-{self.session_id}", daemon=True)
            self._status = Status.RUNNING
        self.hub.publish("lifecycle", {"status": "running", "previous": "initialized", "run_id": self.run_id})
        self.log("INFO", "TRAINING", "Training started", self._config_summary())
        self._thread.start()
        return self.command_result()

    def pause(self) -> dict[str, Any]:
        with self._lock:
            if self._status == Status.PAUSED or (self._status == Status.RUNNING and self._pending == "pause"):
                return self.command_result(idempotent=True)
            if self._status != Status.RUNNING:
                raise ConflictError(f"Cannot pause a session that is {self._status.value}", details={"status": self._status.value})
            self._pending = "pause"
            self._resume.clear()
            self._pause.set()
        return self.command_result()

    def resume(self) -> dict[str, Any]:
        with self._lock:
            if self._status == Status.RUNNING and self._pending != "pause":
                return self.command_result(idempotent=True)
            if self._status not in (Status.PAUSED, Status.RUNNING):
                raise ConflictError(f"Cannot resume a session that is {self._status.value}", details={"status": self._status.value})
            was_paused = self._status == Status.PAUSED
            self._pending = None
            self._pause.clear()
            self._resume.set()
        if was_paused:
            self._set_status(Status.RUNNING, resumed=True)
            self.log("INFO", "TRAINING", "Training resumed", {})
        return self.command_result()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._status in (Status.STOPPING, Status.STOPPED, Status.COMPLETED, Status.FAILED):
                return self.command_result(idempotent=True)
            if self._status == Status.INITIALIZED:
                raise ConflictError("Nothing to stop: the session has not started", details={"status": "initialized"})
            self._status = Status.STOPPING
            self._pending = None
            self._stop.set()
            self._resume.set()
        self.hub.publish("lifecycle", {"status": "stopping", "previous": "running", "run_id": self.run_id})
        return self.command_result()

    def reset(self) -> dict[str, Any]:
        with self._lock:
            if self._status not in RESETTABLE:
                raise ConflictError(
                    f"Stop the session before resetting (status is {self._status.value})",
                    details={"status": self._status.value},
                )
            thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
        with self._lock:
            self.run_index += 1
            self._reset_metrics()
            self._model = None
            self.error = None
            self.started_at = None
            self.finished_at = None
            self._status = Status.INITIALIZED
            self._pending = None
            self._thread = None
        self._build_preview()
        self.hub.publish("reset", {"run_id": self.run_id})
        self.hub.publish("lifecycle", {"status": "initialized", "previous": "reset", "run_id": self.run_id})
        self.log("INFO", "ENVIRONMENT", "Environment reset; metrics cleared for a new run", {"run_id": self.run_id})
        return self.command_result()

    def set_speed(self, speed: float) -> dict[str, Any]:
        spec = next(p for p in TRAINING_PARAMS if p.key == "simulation_speed")
        if not (spec.min <= speed <= spec.max):  # type: ignore[operator]  # NaN fails this too
            raise ValidationError("Invalid simulation speed", details={"errors": [{"field": "speed", "message": f"must be between {spec.min} and {spec.max}"}]})
        self.speed = float(speed)
        self.config["training"]["simulation_speed"] = float(speed)
        self.hub.publish("speed", {"speed": self.speed})
        return self.command_result()

    def command_result(self, idempotent: bool = False) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self._status.value,
            "pending_command": self._pending,
            "idempotent": idempotent,
        }

    def _block_while_paused(self) -> None:
        self._set_status(Status.PAUSED)
        self.log("INFO", "TRAINING", "Training paused", {"timestep": self._timestep})
        paused_at = time.monotonic()
        self._paused_since = paused_at
        while not self._resume.wait(timeout=0.2):
            if self._stop.is_set():
                break
        self._paused_accum += time.monotonic() - paused_at
        self._paused_since = None

    # --------------------------------------------------------------- training

    def _run(self) -> None:
        training = self.config["training"]
        agent = self.config["agent"]
        venv = None
        try:
            seed = int(training["seed"])
            venv = DummyVecEnv([lambda: Monitor(self.definition.make(self.config["env_params"], seed))])
            params = dict(self.config["agent_params"])
            arch = NET_ARCHES[params.pop("net_arch")]
            model = sb3_class(agent)(
                "MlpPolicy",
                venv,
                seed=seed,
                device=training["device"],
                policy_kwargs={"net_arch": arch},
                verbose=0,
                **params,
            )
            model.set_logger(Logger(folder=None, output_formats=[_HubWriter(self)]))
            self._model = model
            self.log("AGENT", "AGENT", f"{agent} model created", {"policy": "MlpPolicy", "net_arch": arch, "device": str(model.device)})
            callback = _StudioCallback(self, self.definition)
            model.learn(total_timesteps=int(training["total_timesteps"]), callback=callback, log_interval=1, progress_bar=False)
            self._timestep = int(model.num_timesteps)
            if training["checkpoint_every"]:
                self._save_checkpoint(model, self._timestep, reason="final")
            self._finish(Status.STOPPED if self._stop.is_set() else Status.COMPLETED)
        except Exception as exc:  # process boundary; state is recorded
            logger.exception("Training session %s failed", self.session_id)
            self.error = f"Training failed with {type(exc).__name__}. See server logs for details."
            self.log("ERROR", "TRAINING", self.error, {})
            self._finish(Status.FAILED)
        finally:
            if venv is not None:
                venv.close()

    def _finish(self, status: Status) -> None:
        self._ended_monotonic = time.monotonic()
        self._flush_episodes(force=True)
        self._maybe_progress(self._timestep, force=True)
        self.finished_at = _now()
        self._set_status(status, error=self.error)
        level = "ERROR" if status == Status.FAILED else "INFO"
        self.log(level, "TRAINING", f"Training {status.value}", {"timestep": self._timestep, "episodes": self._episode_count})
        self._persist()

    # -------------------------------------------------------------- telemetry

    def log(self, level: str, category: str, message: str, meta: dict[str, Any] | None = None, episode: int | None = None) -> None:
        self.hub.publish(
            "log",
            {
                "level": level,
                "category": category,
                "message": message,
                "run_id": self.run_id,
                "episode_id": episode,
                "meta": meta or {},
            },
        )

    def _record_episode(self, *, reward: float, length: int, outcome: dict[str, Any], collisions: int, disturbances: int, timestep: int) -> None:
        with self._lock:
            self._episode_count += 1
            self._timestep = timestep
            self._reward_sum += reward
            self._best_reward = reward if self._best_reward is None else max(self._best_reward, reward)
            self._recent.append(reward)
            self._successes.append(1 if outcome["success"] else 0)
            self._collisions += collisions
            self._disturbances += disturbances
            self._last_termination = outcome["reason"]
            record = {
                "episode": self._episode_count,
                "timestep": timestep,
                "reward": reward,
                "length": length,
                "success": bool(outcome["success"]),
                "reason": outcome["reason"],
                "collisions": collisions,
                "disturbances": disturbances,
                "moving_avg_reward": sum(self._recent) / len(self._recent),
                "success_rate": sum(self._successes) / len(self._successes),
            }
            self._episodes.append(record)
            self._unsent.append(record)
        if collisions:
            self.log("INFO", "ENVIRONMENT", f"{collisions} collision(s) in episode {record['episode']}", {"collisions": collisions}, record["episode"])
        if disturbances and self.definition.disturbances:
            self.log("WARNING", "ENVIRONMENT", f"{disturbances} wind disturbance(s) applied in episode {record['episode']}", {"disturbances": disturbances}, record["episode"])
        self._flush_episodes(force=False)

    def _flush_episodes(self, force: bool) -> None:
        now = time.monotonic()
        if not force and now - self._last_flush < EPISODE_FLUSH_INTERVAL_S:
            return
        with self._lock:
            batch, self._unsent = self._unsent, []
        self._last_flush = now
        if batch:
            self.hub.publish("episodes", {"episodes": batch, "run_id": self.run_id})
            last = batch[-1]
            if len(batch) == 1 or last["episode"] % 10 == 0:
                self.log(
                    "INFO",
                    "TRAINING",
                    f"Episode {last['episode']} {last['reason']} (reward {last['reward']:.2f}, {last['length']} steps)",
                    {"batched_episodes": len(batch), "moving_avg_reward": last["moving_avg_reward"]},
                    last["episode"],
                )

    def _elapsed(self) -> float:
        """Wall-clock training time, excluding time spent paused."""
        if self._started_monotonic is None:
            return 0.0
        end = self._ended_monotonic if self._ended_monotonic is not None else time.monotonic()
        paused = self._paused_accum
        if self._paused_since is not None and self._ended_monotonic is None:
            paused += time.monotonic() - self._paused_since
        return max(0.0, end - self._started_monotonic - paused)

    def _progress_payload(self, timestep: int) -> dict[str, Any]:
        total = int(self.config["training"]["total_timesteps"])
        elapsed = self._elapsed()
        return {
            "run_id": self.run_id,
            "timestep": timestep,
            "total_timesteps": total,
            "fraction": min(1.0, timestep / total) if total else 0.0,
            "episodes": self._episode_count,
            "elapsed_seconds": elapsed,
            "steps_per_second": (timestep / elapsed) if elapsed > 0 else 0.0,
            "current_reward_avg": (sum(self._recent) / len(self._recent)) if self._recent else None,
            "mean_reward": (self._reward_sum / self._episode_count) if self._episode_count else None,
            "best_reward": self._best_reward,
            "success_rate": (sum(self._successes) / len(self._successes)) if self._successes else None,
            "collisions": self._collisions,
            "disturbances": self._disturbances,
            "last_termination": self._last_termination,
            "env_state": dict(self._last_state),
            "speed": self.speed,
        }

    def _maybe_progress(self, timestep: int, force: bool) -> None:
        now = time.monotonic()
        self._timestep = timestep
        if not force and now - self._last_progress < PROGRESS_INTERVAL_S:
            return
        self._last_progress = now
        self._flush_episodes(force=force)
        self.hub.publish("progress", self._progress_payload(timestep))

    def _on_algorithm_stats(self, key_values: dict[str, Any], step: int) -> None:
        stats: dict[str, float] = {}
        for key, name in _UPDATE_KEYS.items():
            if key in key_values:
                stats[name] = float(key_values[key])
        if "train/entropy_loss" in key_values:
            stats["entropy"] = -float(key_values["train/entropy_loss"])
        if not any(k in stats for k in ("policy_loss", "value_loss", "loss")):
            return
        record = {"timestep": int(self._timestep), "update": len(self._updates) + 1, **stats}
        with self._lock:
            self._updates.append(record)
        self.hub.publish("update", {"run_id": self.run_id, **record})

    def _evaluate(self, model: Any, timestep: int) -> None:
        training = self.config["training"]
        env = self.definition.make(self.config["env_params"], int(training["seed"]) + 10_000)
        rewards: list[float] = []
        lengths: list[int] = []
        successes = 0
        try:
            for index in range(int(training["eval_episodes"])):
                obs, info = env.reset(seed=int(training["seed"]) + 10_000 + index)
                total, steps, terminated, truncated = 0.0, 0, False, False
                while not (terminated or truncated):
                    if self._stop.is_set():
                        return
                    action, _ = model.predict(obs, deterministic=True)
                    obs, reward, terminated, truncated, info = env.step(action)
                    total += float(reward)
                    steps += 1
                outcome = self.definition.classify(self.config["env_params"], None, info, bool(terminated))
                successes += int(outcome["success"])
                rewards.append(total)
                lengths.append(steps)
        finally:
            env.close()
        count = len(rewards)
        mean = sum(rewards) / count
        std = (sum((r - mean) ** 2 for r in rewards) / count) ** 0.5
        record = {
            "timestep": timestep,
            "episodes": count,
            "mean_reward": mean,
            "std_reward": std,
            "mean_length": sum(lengths) / count,
            "success_rate": successes / count,
        }
        self._evals.append(record)
        self.hub.publish("evaluation", {"run_id": self.run_id, **record})
        self.log("INFO", "TRAINING", f"Evaluation at {timestep}: mean reward {mean:.2f} ± {std:.2f}, success {record['success_rate']:.0%}", record)

    def _save_checkpoint(self, model: Any, timestep: int, reason: str) -> None:
        checkpoint_id = f"ckpt_{uuid.uuid4().hex[:12]}"
        directory = data_dir() / "checkpoints" / self.session_id
        tmp_path = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            final = directory / f"{checkpoint_id}.zip"
            fd, tmp_name = tempfile.mkstemp(prefix="ckpt_", suffix=".tmp", dir=directory)
            tmp_path = Path(tmp_name)
            with os.fdopen(fd, "wb") as handle:
                model.save(handle)
                handle.flush()
                os.fsync(handle.fileno())
            digest = hashlib.sha256(tmp_path.read_bytes()).hexdigest()
            os.replace(tmp_path, final)
            tmp_path = None
            record = {
                "checkpoint_id": checkpoint_id,
                "session_id": self.session_id,
                "run_id": self.run_id,
                "timestep": timestep,
                "reason": reason,
                "sha256": digest,
                "size_bytes": final.stat().st_size,
                "created_at": _now(),
                "algorithm": self.config["agent"],
                "environment": self.config["environment"],
            }
            (directory / f"{checkpoint_id}.meta.json").write_text(json.dumps(record, sort_keys=True))
            with self._lock:
                self._checkpoints.append(record)
            self.hub.publish("checkpoint", record)
            self.log("INFO", "CHECKPOINT", f"Checkpoint saved at timestep {timestep} ({reason})", {"checkpoint_id": checkpoint_id, "sha256": digest[:12]})
        except OSError:
            logger.exception("Checkpoint write failed for %s", self.session_id)
            self.log("ERROR", "CHECKPOINT", "Checkpoint could not be written", {"timestep": timestep})
        finally:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def _persist(self) -> None:
        """Write a durable experiment record for later inspection."""
        directory = data_dir() / "sessions"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            record = self.summary()
            record["episodes"] = list(self._episodes)
            record["updates"] = list(self._updates)
            record["evaluations"] = self._evals
            target = directory / f"{self.session_id}_r{self.run_index}.json"
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps(record))
            os.replace(tmp, target)
        except OSError:
            logger.exception("Could not persist session %s", self.session_id)

    # --------------------------------------------------------------- snapshots

    def summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "name": self.name,
            "status": self._status.value,
            "pending_command": self._pending,
            "agent": self.config["agent"],
            "environment": self.config["environment"],
            "config": self.config,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "progress": self._progress_payload(self._timestep),
            "checkpoints": list(self._checkpoints),
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            data = self.summary()
            data["scene"] = self._scene
            data["episodes"] = list(self._episodes)
            data["updates"] = list(self._updates)
            data["evaluations"] = list(self._evals)
            data["logs"] = self.hub.recent("log", 500)
            data["seq"] = self.hub.last_seq()
        frame = self.hub.latest_frame()
        data["frame"] = frame["payload"] if frame else None
        return data
