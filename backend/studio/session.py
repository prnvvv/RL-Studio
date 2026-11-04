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

import numpy as np
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.logger import KVWriter, Logger
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from backend.database.exceptions import ConflictError, NotFoundError, ValidationError

from . import custom
from .brain import GRID_REFRESH_FRAMES, compute_brain, compute_grid_brain
from .catalog import (
    AGENTS,
    OFF_POLICY_REPLAY,
    RECURRENT,
    TRAINING_PARAMS,
    build_model,
)
from .controls import RuntimeControls, validate_action
from .envs import EnvDefinition, describe_space, unavailable_reason
from .hub import SessionHub
from .params import validate_params
from .provenance_bridge import RunBridge, resolve_environment_version
from .store import RunRecorder
from .wrappers import ChaosEnv, HumanControlEnv

logger = logging.getLogger(__name__)

BASE_STEPS_PER_SECOND = 30.0  # 1x playback speed
FRAME_INTERVAL_S = 1.0 / 30.0
PROGRESS_INTERVAL_S = 0.5
EPISODE_FLUSH_INTERVAL_S = 0.15
MAX_EPISODES_KEPT = 5000
MAX_UPDATES_KEPT = 2000
RECENT_WINDOW = 20
CHAOS_LOG_INTERVAL_S = 0.5


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
    "train/actor_loss": "actor_loss",
    "train/critic_loss": "critic_loss",
    "train/ent_coef": "ent_coef",
    "train/ent_coef_loss": "ent_coef_loss",
    "rollout/exploration_rate": "exploration_rate",
}


def data_dir() -> Path:
    override = os.environ.get("STUDIO_DATA_DIR")
    base = Path(override) if override else Path(__file__).resolve().parents[2] / "var" / "studio"
    return base


def store_path() -> Path:
    return data_dir() / "studio.sqlite3"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise a session request; raises ``ValidationError``."""
    agent_key = raw.get("agent")
    env_key = raw.get("environment")
    errors: list[dict[str, str]] = []
    model = None
    if custom.is_custom_agent(agent_key):
        try:
            model = custom.get_model(agent_key)
        except NotFoundError:
            errors.append({"field": "agent", "message": "uploaded model not found; it may have been deleted"})
    elif agent_key not in AGENTS:
        errors.append({"field": "agent", "message": f"unknown agent {agent_key!r}"})
    definition = custom.resolve_environment(env_key)
    if definition is None:
        errors.append({"field": "environment", "message": f"unknown environment {env_key!r}"})
    elif (missing := unavailable_reason(definition)) is not None:
        errors.append({"field": "environment", "message": f"{definition.name} cannot run here: {missing}"})
    if errors:
        raise ValidationError("Invalid configuration", details={"errors": errors})

    probe = definition.make(validate_params(definition.params, {}, scope="env_params"), 0)
    try:
        obs_desc, act_desc = describe_space(probe.observation_space), describe_space(probe.action_space)
    finally:
        probe.close()
    if model is not None:
        reason = custom.incompatibility(model, obs_desc, act_desc, definition.name)
        if reason:
            raise ValidationError("Incompatible model and environment", details={"errors": [{"field": "agent", "message": reason}]})
        agent_params = validate_params((), raw.get("agent_params"), scope="agent_params")
        env_params = validate_params(definition.params, raw.get("env_params"), scope="env_params")
        training = validate_params(TRAINING_PARAMS, raw.get("training"), scope="training")
        # Inference never learns, so the checkpoint/eval settings are stored but unused.
        return {"agent": agent_key, "environment": env_key, "agent_params": agent_params, "env_params": env_params, "training": training}

    agent = AGENTS[agent_key]
    if act_desc["type"] not in agent.action_spaces:
        raise ValidationError(
            "Incompatible agent and environment",
            details={"errors": [{"field": "agent", "message": f"{agent_key} does not support {act_desc['type']} actions"}]},
        )

    agent_params = validate_params(agent.params, raw.get("agent_params"), scope="agent_params")
    env_params = validate_params(definition.params, raw.get("env_params"), scope="env_params")
    training = validate_params(TRAINING_PARAMS, raw.get("training"), scope="training")

    cross: list[dict[str, str]] = []
    if definition.check is not None:
        try:
            definition.check(env_params)
        except ValueError as exc:
            field, _, message = str(exc).partition(": ")
            cross.append({"field": f"env_params.{field}" if message else "env_params", "message": message or str(exc)})
    if "batch_size" in agent_params and agent_key in ("PPO", "PPO_LSTM") and agent_params["batch_size"] > agent_params["n_steps"]:
        cross.append({"field": "agent_params.batch_size", "message": "must not exceed steps per update"})
    if agent_key in OFF_POLICY_REPLAY and agent_params["learning_starts"] >= training["total_timesteps"]:
        cross.append({"field": "agent_params.learning_starts", "message": "must be below total timesteps"})
    if agent_key in OFF_POLICY_REPLAY and agent_params["buffer_size"] < agent_params["batch_size"]:
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
        self._brain_frames = 0
        self._grid_cache: list[dict[str, Any]] | None = None

    def _on_step(self) -> bool:
        last_obs = getattr(self.model, "_last_obs", None)
        locals_ = self.locals
        info = locals_["infos"][0]
        action = locals_["actions"][0]
        if info.get("action_source") == "human":
            action = self._adopt_human_action(locals_, info["executed_action"])
        return self.step(
            env=self.training_env.envs[0],
            timestep=int(self.num_timesteps),
            pre_obs=None if last_obs is None else last_obs[0],
            new_obs=locals_["new_obs"][0],
            action=action,
            reward=float(locals_["rewards"][0]),
            done=bool(locals_["dones"][0]),
            info=info,
            model=self.model,
        )

    def _adopt_human_action(self, locals_: dict[str, Any], executed: Any) -> Any:
        """Make the learning buffers record the action the human actually executed.

        SB3 picks the action before this callback runs, so without this the
        replay/rollout buffer would pair the human's reward with the policy's
        action. DQN stores the executed action directly. PPO/A2C also need the
        log-probability and value of that action under the current policy.
        Human steps remain off-policy for on-policy algorithms; this only keeps
        the stored transition self-consistent.
        """
        action = np.asarray(executed)
        try:
            buffer_actions = locals_.get("buffer_actions")
            if buffer_actions is not None:  # off-policy (DQN)
                buffer_actions[0] = action
            elif "log_probs" in locals_ and "obs_tensor" in locals_:  # on-policy (PPO/A2C)
                import torch

                actions = locals_["actions"]
                actions[0] = action
                with torch.no_grad():
                    values, log_prob, _ = self.model.policy.evaluate_actions(
                        locals_["obs_tensor"], torch.as_tensor(actions, device=self.model.device)
                    )
                locals_["log_probs"].copy_(log_prob.reshape(locals_["log_probs"].shape))
                locals_["values"].copy_(values.reshape(locals_["values"].shape))
        except (KeyError, IndexError, RuntimeError, ValueError):
            logger.warning("Could not align learning buffers with a human action", exc_info=True)
        return action[()] if action.ndim == 0 else action

    def step(self, *, env: Any, timestep: int, pre_obs: Any, new_obs: Any, action: Any, reward: float, done: bool, info: dict[str, Any], model: Any, policy: Any = None) -> bool:
        """Handle one environment transition. Returns False to stop the run.

        Shared by SB3 training (via ``_on_step``) and inference-only sessions, so
        frames, episodes, persistence and pacing behave identically in both.
        """
        s = self.s
        if s._stop.is_set():
            return False
        if s._pause.is_set():
            s._block_while_paused()
            self._next_t = time.monotonic()
            if s._stop.is_set():
                return False

        action_value: Any = int(action) if getattr(action, "ndim", 1) == 0 else [float(a) for a in action]

        collision = bool(info.get("collision", False))
        disturbed = bool(info.get("disturbance", False))
        self._episode_reward += reward
        self._episode_steps += 1
        self._episode_collisions += int(collision)
        self._episode_disturbances += int(disturbed)

        terminal_obs = info.get("terminal_observation") if done else None
        outcome: dict[str, Any] | None = None
        truncated = bool(info.get("TimeLimit.truncated", False)) if done else False
        if s._recorder is not None:
            s._recorder.add_step(
                step_index=timestep,
                episode_step=self._episode_steps,
                obs=pre_obs,
                action=action_value,
                reward=reward,
                terminated=done and not truncated,
                truncated=truncated,
                next_obs=terminal_obs if done and terminal_obs is not None else new_obs,
                source=str(info.get("action_source", "agent")),
                chaos=",".join(sorted({e["kind"] for e in info.get("chaos", [])})),
            )
        if info.get("chaos"):
            s._register_chaos(info["chaos"])
        if done:
            outcome = self.definition.classify(s.config["env_params"], terminal_obs, info, not truncated)
        now = time.monotonic()
        if done or now - self._last_frame >= FRAME_INTERVAL_S:
            self._last_frame = now
            payload: dict[str, Any] = {
                "timestep": timestep,
                "episode": s._episode_count + 1,
                "episode_step": self._episode_steps,
                "action": action_value,
                "source": str(info.get("action_source", "agent")),
                "reward": reward,
                "episode_reward": self._episode_reward,
                "collision": collision,
                "disturbance": disturbed,
                "done": done,
                "state": self.definition.frame_state(env, terminal_obs),
            }
            if outcome is not None:
                payload["outcome"] = outcome
            if s.controls.brain_enabled:
                brain = self._brain_payload(policy if policy is not None else getattr(model, "policy", None), pre_obs, action_value)
                if brain is not None:
                    payload["brain"] = brain
            s._last_state = payload["state"]
            s.hub.set_frame(payload)

        if outcome is not None:
            s._record_episode(
                truncated=bool(truncated),
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
        if model is not None and training["checkpoint_every"] and timestep - self._last_checkpoint >= training["checkpoint_every"]:
            self._last_checkpoint = timestep
            s._save_checkpoint(model, timestep, reason="interval")
        if model is not None and training["eval_every"] and timestep - self._last_eval >= training["eval_every"]:
            self._last_eval = timestep
            s._evaluate(model, timestep)

        self._pace()
        return True

    def _brain_payload(self, policy: Any, obs: Any, executed: Any) -> dict[str, Any] | None:
        """The policy's current preferences, or None (and the view is switched off) if it cannot be read."""
        s = self.s
        try:
            brain = compute_brain(policy, obs, executed)
            if brain is not None:
                if self._brain_frames % GRID_REFRESH_FRAMES == 0:
                    self._grid_cache = compute_grid_brain(policy, s._scene)
                self._brain_frames += 1
                if self._grid_cache:
                    brain["grid"] = self._grid_cache
            return brain
        except (RuntimeError, ValueError, TypeError, AttributeError, KeyError):
            logger.warning("Policy introspection failed for %s", s.session_id, exc_info=True)
            s.controls.set_brain(False)
            s.hub.publish("control", {"run_id": s.run_id, **s.controls.snapshot()})
            s.log("WARNING", "AGENT", "The agent brain view was switched off: this policy cannot be inspected", {})
            return None

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
    def __init__(
        self,
        session_id: str,
        config: dict[str, Any],
        name: str | None = None,
        battle_id: str | None = None,
        battle_side: str | None = None,
        project_id: str | None = None,
    ) -> None:
        self.session_id = session_id
        # Association only (kept out of ``config`` so config fingerprints and stored configs are unchanged).
        self.project_id = project_id
        self.battle_id = battle_id
        self.battle_side = battle_side
        self.config = config
        self.definition = custom.resolve_environment(config["environment"])  # type: ignore[assignment]
        self.model_record = custom.get_model(config["agent"]) if custom.is_custom_agent(config["agent"]) else None
        self.mode = "inference" if self.model_record else "training"
        agent_label = self.model_record["name"] if self.model_record else config["agent"]
        builtin_env = config["environment"] in ("cartpole", "warehouse")
        self.name = name or f"{agent_label} on {config['environment'] if builtin_env else self.definition.name}"
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
        self._recorder: RunRecorder | None = None
        self._bridge: RunBridge | None = None
        self._environment_version: str | None = None
        self.controls = RuntimeControls()
        self._action_space: Any = None
        self._chaos_pending: dict[str, int] = {}
        self._chaos_last_log = 0.0
        self._obs_shape: list[int] | None = None
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
            self._obs_shape = [int(d) for d in env.observation_space.shape]
            self._environment_version = resolve_environment_version(env)
            self._action_space = env.action_space
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

    # ---------------------------------------------------------------- chaos mode

    def _register_chaos(self, events: list[dict[str, Any]]) -> None:
        """Count disturbances and log them as FAULT events, batched so a busy run cannot flood the console.

        Sensor noise is continuous background; it is counted per step and announced when chaos
        mode is switched on, not logged on every step. A forced noise burst is logged.
        """
        with self._lock:
            for event in events:
                if event["kind"] == "sensor_noise" and not event.get("forced"):
                    self.controls.chaos_noise_steps += 1
                    continue
                self._chaos_pending[event["kind"]] = self._chaos_pending.get(event["kind"], 0) + 1
                self.controls.chaos_events += 1
        self._flush_chaos_log(force=False)

    def _flush_chaos_log(self, force: bool) -> None:
        now = time.monotonic()
        if not self._chaos_pending or (not force and now - self._chaos_last_log < CHAOS_LOG_INTERVAL_S):
            return
        with self._lock:
            pending, self._chaos_pending = self._chaos_pending, {}
        self._chaos_last_log = now
        summary = ", ".join(f"{count}× {kind.replace('_', ' ')}" for kind, count in sorted(pending.items()))
        self.log("WARNING", "FAULT", f"Chaos injected: {summary}", {"counts": pending, "timestep": self._timestep})

    def set_chaos(self, enabled: bool | None, intensity: float | None, kinds: list[str] | None) -> dict[str, Any]:
        supported = self.definition.chaos_kinds
        with self._lock:
            if self._status in (Status.STOPPING, Status.STOPPED, Status.COMPLETED, Status.FAILED):
                raise ConflictError(
                    f"Cannot change chaos mode of a session that is {self._status.value}",
                    details={"status": self._status.value},
                )
        if not supported:
            raise ValidationError("This environment does not support chaos mode")
        if kinds is not None:
            unknown = sorted(set(kinds) - set(supported))
            if unknown:
                raise ValidationError(
                    "Unsupported disturbance",
                    details={"errors": [{"field": "kinds", "message": f"{unknown} not available; choose from {list(supported)}"}]},
                )
        previous_enabled, _, previous_kinds = self.controls.chaos_config()
        chosen = tuple(kinds) if kinds is not None else (previous_kinds or (tuple(supported) if enabled else ()))
        self.controls.configure_chaos(enabled, intensity, chosen)
        now_enabled, now_intensity, now_kinds = self.controls.chaos_config()
        self.hub.publish("control", {"run_id": self.run_id, **self.controls.snapshot()})
        if now_enabled and not previous_enabled:
            self.log("WARNING", "FAULT", f"Chaos mode enabled: intensity {now_intensity:.2f}, disturbances: {', '.join(now_kinds) or 'none selected'}", {})
        elif previous_enabled and not now_enabled:
            self._flush_chaos_log(force=True)
            self.log("INFO", "FAULT", "Chaos mode disabled", {"events": self.controls.chaos_events})
        elif now_enabled:
            self.log("INFO", "FAULT", f"Chaos settings changed: intensity {now_intensity:.2f}, disturbances: {', '.join(now_kinds)}", {})
        return self.command_result()

    def trigger_chaos(self, kind: str) -> dict[str, Any]:
        with self._lock:
            if self._status not in (Status.RUNNING, Status.PAUSED):
                raise ConflictError(
                    f"Chaos can only be triggered in a running session (status is {self._status.value})",
                    details={"status": self._status.value},
                )
        if kind not in self.definition.chaos_kinds:
            raise ValidationError(
                "Unsupported disturbance",
                details={"errors": [{"field": "kind", "message": f"choose from {list(self.definition.chaos_kinds)}"}]},
            )
        self.controls.trigger_chaos(kind)
        self.log("WARNING", "FAULT", f"Chaos triggered manually: {kind.replace('_', ' ')}", {"kind": kind})
        return self.command_result()

    def _build_env(self, seed: int) -> Any:
        """The environment the training/inference loop steps (wrappers read ``self.controls``)."""
        env = self.definition.make(self.config["env_params"], seed)
        env = ChaosEnv(env, self.controls, seed, self.definition.noise_scale)
        env = HumanControlEnv(env, self.controls, self.definition.human_sticky, self._stop.is_set)
        return Monitor(env)

    # ---------------------------------------------------------- manual control

    def set_human_control(self, active: bool) -> dict[str, Any]:
        with self._lock:
            if self._status in (Status.STOPPING, Status.STOPPED, Status.COMPLETED, Status.FAILED):
                raise ConflictError(
                    f"Cannot change manual control of a session that is {self._status.value}",
                    details={"status": self._status.value},
                )
        if active:
            reason = self._manual_unsupported()
            if reason:
                raise ConflictError(reason, details={"agent": self.config["agent"], "environment": self.config["environment"]})
        changed = self.controls.set_human(active)
        if changed:
            self.hub.publish("control", {"run_id": self.run_id, **self.controls.snapshot()})
            if active:
                self.log("INFO", "AGENT", "Manual control taken: your actions replace the agent's and are recorded with source=human", {})
                if self.mode == "training" and self.config["agent"] in ("PPO", "A2C"):
                    self.log("WARNING", "AGENT", "Learning from human steps is off-policy for on-policy algorithms", {"agent": self.config["agent"]})
            else:
                self.log("INFO", "AGENT", "Manual control released: the agent is acting again", {"human_steps": self.controls.human_steps})
        return self.command_result()

    def _manual_unsupported(self) -> str | None:
        if not self.definition.manual:
            return f"{self.definition.name} has no keyboard mapping, so it cannot be driven manually"
        agent = AGENTS.get(self.config["agent"])
        if agent is not None and not agent.supports_manual:
            return f"{agent.name} cannot be taken over manually (its policy is not a feed-forward discrete controller)"
        return None

    def set_brain_view(self, enabled: bool) -> dict[str, Any]:
        """Stream the policy's action preferences with every frame while enabled."""
        with self._lock:
            if self._status in (Status.STOPPING, Status.STOPPED, Status.COMPLETED, Status.FAILED):
                raise ConflictError(
                    f"Cannot change the brain view of a session that is {self._status.value}",
                    details={"status": self._status.value},
                )
        agent = AGENTS.get(self.config["agent"])
        if enabled and agent is not None and not agent.supports_brain:
            raise ConflictError(
                f"The brain view is not available for {agent.name}: it has no inspectable action distribution",
                details={"agent": agent.key},
            )
        if self.controls.set_brain(enabled):
            self.hub.publish("control", {"run_id": self.run_id, **self.controls.snapshot()})
            self.log("INFO", "AGENT", "Agent brain view " + ("enabled" if enabled else "disabled"), {})
        return self.command_result()

    def submit_human_action(self, action: Any) -> dict[str, Any]:
        if not self.controls.human_active:
            raise ConflictError("Manual control is not active", details={"status": self._status.value})
        valid = validate_action(self._action_space, action)
        self.controls.submit_action(valid)
        return {"accepted": True}

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
            self._recorder = RunRecorder(store_path(), self.run_id)
            self._recorder.start_run(
                session_id=self.session_id,
                run_index=self.run_index,
                name=self.name,
                agent=self.config["agent"],
                environment=self.config["environment"],
                mode=self.mode,
                config=self.config,
                obs_shape=self._obs_shape,
                created_at=self.created_at,
                started_at=self.started_at,
            )
            self._bridge = RunBridge(
                self.run_id,
                environment_id=self.config["environment"],
                environment_version=self._environment_version,
                agent_id=self.config["agent"],
                config=self.config,
                project_id=self.project_id,
            )
            self._bridge.run_started()
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
            self._recorder = None
            self._bridge = None
            self.controls = RuntimeControls()
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

    def _run_inference(self) -> None:
        """Run an uploaded policy for ``total_timesteps`` steps; nothing is learned."""
        training = self.config["training"]
        venv = None
        try:
            seed = int(training["seed"])
            venv = DummyVecEnv([lambda: self._build_env(seed)])
            venv.seed(seed)
            policy = custom.load_policy(self.model_record, venv.observation_space, venv.action_space)  # type: ignore[arg-type]
            self._model = policy
            record = self.model_record or {}
            self.log("AGENT", "AGENT", f"Loaded uploaded model {record.get('name')!r} for inference", {"algorithm": record.get("algorithm"), "sha256": str(record.get("sha256"))[:12]})
            callback = _StudioCallback(self, self.definition)
            obs = venv.reset()
            timestep = 0
            total = int(training["total_timesteps"])
            while timestep < total:
                action, _ = policy.predict(obs, deterministic=True)
                new_obs, rewards, dones, infos = venv.step(action)
                if infos[0].get("action_source") == "human":
                    action = np.asarray([infos[0]["executed_action"]])
                timestep += 1
                keep_going = callback.step(
                    env=venv.envs[0],
                    timestep=timestep,
                    pre_obs=obs[0],
                    new_obs=new_obs[0],
                    action=action[0],
                    reward=float(rewards[0]),
                    done=bool(dones[0]),
                    info=infos[0],
                    model=None,
                    policy=policy,
                )
                obs = new_obs
                if not keep_going:
                    break
            self._timestep = timestep
            self._finish(Status.STOPPED if self._stop.is_set() else Status.COMPLETED)
        except (ValidationError, NotFoundError) as exc:
            self.error = f"Model could not be used: {exc.message}"
            self.log("ERROR", "AGENT", self.error, {})
            self._finish(Status.FAILED)
        except Exception as exc:  # process boundary; state is recorded
            logger.exception("Inference session %s failed", self.session_id)
            self.error = f"Inference failed with {type(exc).__name__}. See server logs for details."
            self.log("ERROR", "TRAINING", self.error, {})
            self._finish(Status.FAILED)
        finally:
            if venv is not None:
                venv.close()

    def _run(self) -> None:
        if self.mode == "inference":
            self._run_inference()
            return
        training = self.config["training"]
        agent = self.config["agent"]
        venv = None
        try:
            seed = int(training["seed"])
            venv = DummyVecEnv([lambda: self._build_env(seed)])
            model, created = build_model(agent, venv, self.config["agent_params"], seed=seed, device=training["device"])
            model.set_logger(Logger(folder=None, output_formats=[_HubWriter(self)]))
            self._model = model
            self.log("AGENT", "AGENT", f"{agent} model created", {**created, "device": str(model.device)})
            callback = _StudioCallback(self, self.definition)
            model.learn(total_timesteps=int(training["total_timesteps"]), callback=callback, log_interval=1, progress_bar=False)
            self._timestep = int(model.num_timesteps)
            if training["checkpoint_every"]:
                self._save_checkpoint(model, self._timestep, reason="final")
            self._finish(Status.STOPPED if self._stop.is_set() else Status.COMPLETED)
        except Exception as exc:  # process boundary; state is recorded
            logger.exception("Training session %s failed", self.session_id)
            self.error = f"Training failed with {type(exc).__name__}. See server logs for details."
            self.log("ERROR", "TRAINING", self.error, {"exception": type(exc).__name__, "detail": str(exc)[:300]})
            self._finish(Status.FAILED)
        finally:
            if venv is not None:
                venv.close()

    def _finish(self, status: Status) -> None:
        self.controls.set_human(False)
        self._flush_chaos_log(force=True)
        self._ended_monotonic = time.monotonic()
        self._flush_episodes(force=True)
        self._maybe_progress(self._timestep, force=True)
        self.finished_at = _now()
        if self._recorder is not None:
            self._recorder.finish_run(status=status.value, finished_at=self.finished_at, error=self.error)
            if not self._recorder.healthy:
                self.log("ERROR", "TRAINING", "Trajectory data could not be fully saved", {"detail": self._recorder.last_error})
        if self._bridge is not None:
            self._bridge.run_finished(status=status.value, timestep=self._timestep, error=self.error)
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

    def _record_episode(self, *, truncated: bool | None = None, reward: float, length: int, outcome: dict[str, Any], collisions: int, disturbances: int, timestep: int) -> None:
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
        if self._recorder is not None:
            self._recorder.end_episode(end_step=timestep, reward=reward, length=length, success=bool(outcome["success"]), reason=outcome["reason"], collisions=collisions, disturbances=disturbances)
        if self._bridge is not None:
            self._bridge.episode_ended(
                episode=record["episode"], timestep=timestep, reward=reward, length=length,
                success=bool(outcome["success"]), reason=outcome["reason"], collisions=collisions,
                disturbances=disturbances, truncated=truncated,
            )
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
            # Reward of finished episodes per environment step (a throughput-independent score).
            "reward_per_step": (self._reward_sum / timestep) if timestep and self._episode_count else None,
            "best_reward": self._best_reward,
            "success_rate": (sum(self._successes) / len(self._successes)) if self._successes else None,
            "collisions": self._collisions,
            "disturbances": self._disturbances,
            "last_termination": self._last_termination,
            # Scalars only: point lists (terrain, obstacles) belong to frames, not to progress readouts.
            "env_state": {k: v for k, v in self._last_state.items() if isinstance(v, (int, float)) and not isinstance(v, bool)},
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
        if not any(k in stats for k in ("policy_loss", "value_loss", "loss", "actor_loss", "critic_loss")):
            return
        record = {"timestep": int(self._timestep), "update": len(self._updates) + 1, **stats}
        with self._lock:
            self._updates.append(record)
        if self._recorder is not None:
            self._recorder.add_update(record["timestep"], stats)
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
                lstm_state, episode_start = None, np.ones((1,), dtype=bool)  # recurrent policies carry memory
                while not (terminated or truncated):
                    if self._stop.is_set():
                        return
                    if self.config["agent"] in RECURRENT:
                        action, lstm_state = model.predict(obs, state=lstm_state, episode_start=episode_start, deterministic=True)
                        episode_start = np.zeros((1,), dtype=bool)
                    else:
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
        if self._recorder is not None:
            self._recorder.add_evaluation(timestep, record)
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
            if self._recorder is not None:
                self._recorder.add_checkpoint(record, str(final.relative_to(data_dir())))
            if self._bridge is not None:
                self._bridge.checkpoint_saved(record, final)
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
            "project_id": self.project_id,
            "name": self.name,
            "status": self._status.value,
            "pending_command": self._pending,
            "agent": self.config["agent"],
            "environment": self.config["environment"],
            "mode": self.mode,
            "battle": {"battle_id": self.battle_id, "side": self.battle_side} if self.battle_id else None,
            "controls": self.controls.snapshot(),
            "config": self.config,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "progress": self._progress_payload(self._timestep),
            "checkpoints": list(self._checkpoints),
            "persistence": {
                "healthy": self._recorder.healthy if self._recorder else True,
                "error": self._recorder.last_error if self._recorder else None,
            },
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
