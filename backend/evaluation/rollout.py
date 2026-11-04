"""Real policy rollouts for evaluation.

Loads a *saved checkpoint* (a registered, hash-verified artifact) and plays episodes against the environment it was
trained in. Nothing here invents a metric: every number comes from an episode that was actually stepped. A policy that
cannot be loaded, an environment that cannot run, or an episode that raises is reported, never replaced by a default.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from backend.studio.catalog import RECURRENT, sb3_class
from backend.studio.envs import ENVIRONMENTS, EnvDefinition, unavailable_reason
from backend.studio.provenance_bridge import resolve_environment_version

from .models import EpisodeEvaluation

logger = logging.getLogger(__name__)

#: Held-out seeds start far from the usual training seeds (0, 1, ...) so evaluation is not on training episodes.
DEFAULT_BASE_SEED = 100_000
MAX_EPISODES = 100
#: A rollout never runs longer than this per episode, whatever the environment's own limit says.
HARD_STEP_CAP = 20_000


class RolloutError(Exception):
    """The evaluation could not be run (as opposed to the policy performing badly)."""


def environment_definition(environment_id: str | None) -> EnvDefinition:
    definition = ENVIRONMENTS.get(environment_id or "")
    if definition is None:
        raise RolloutError(
            f"Environment {environment_id!r} is not a built-in environment, so a saved policy cannot be "
            "rolled out against it here."
        )
    reason = unavailable_reason(definition)
    if reason is not None:
        raise RolloutError(f"Environment {environment_id!r} cannot run: {reason}")
    return definition


def default_env_params(definition: EnvDefinition) -> dict[str, Any]:
    return {spec.key: spec.default for spec in definition.params}


def load_policy(path: Path, algorithm: str) -> Any:
    try:
        cls = sb3_class(algorithm)
    except (KeyError, ImportError, AttributeError) as exc:
        raise RolloutError(f"Algorithm {algorithm!r} is not available in this deployment.") from exc
    try:
        return cls.load(str(path), device="cpu")
    except Exception as exc:
        logger.warning("checkpoint load failed (%s)", type(exc).__name__)
        raise RolloutError(f"The checkpoint could not be loaded as a {algorithm} policy ({type(exc).__name__}).") from exc


def environment_version_of(definition: EnvDefinition, env_params: dict[str, Any]) -> str | None:
    env = definition.make(env_params, 0)
    try:
        return resolve_environment_version(env)
    finally:
        env.close()


def rollout(
    model: Any,
    *,
    algorithm: str,
    definition: EnvDefinition,
    env_params: dict[str, Any],
    seeds: list[int],
) -> list[EpisodeEvaluation]:
    """Play one deterministic episode per seed. An episode that raises is recorded with its error, not dropped."""
    episodes: list[EpisodeEvaluation] = []
    for seed in seeds:
        env = definition.make(env_params, seed)
        try:
            episodes.append(_play(model, algorithm, definition, env_params, env, seed))
        except Exception as exc:  # noqa: BLE001
            logger.warning("evaluation episode failed (%s)", type(exc).__name__)
            episodes.append(
                EpisodeEvaluation(seed=seed, reward=0.0, episode_length=0, success=False,
                                  error=f"episode raised {type(exc).__name__}")
            )
        finally:
            env.close()
    return episodes


def _play(model: Any, algorithm: str, definition: EnvDefinition, env_params: dict[str, Any], env: Any, seed: int) -> EpisodeEvaluation:
    obs, info = env.reset(seed=seed)
    total, steps, terminated, truncated, collisions = 0.0, 0, False, False, 0
    lstm_state, episode_start = None, np.ones((1,), dtype=bool)
    while not (terminated or truncated) and steps < HARD_STEP_CAP:
        if algorithm in RECURRENT:
            action, lstm_state = model.predict(obs, state=lstm_state, episode_start=episode_start, deterministic=True)
            episode_start = np.zeros((1,), dtype=bool)
        else:
            action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)
        total += float(reward)
        steps += 1
        collisions += int(bool(info.get("collision"))) if isinstance(info, dict) else 0
    capped = not (terminated or truncated)
    outcome = definition.classify(env_params, None, info if isinstance(info, dict) else {}, bool(terminated))
    return EpisodeEvaluation(
        seed=seed,
        reward=total,
        episode_length=steps,
        success=bool(outcome["success"]) and not capped,
        collision=collisions > 0,
        timed_out=bool(truncated) or capped,
        error=None,
        metadata={"reason": outcome.get("reason"), "capped": capped},
    )


def variability(episodes: list[EpisodeEvaluation]) -> dict[str, Any]:
    """Spread of the valid episodes' rewards and lengths (population std; ``None`` when there are no valid episodes)."""
    valid = [e for e in episodes if e.error is None]
    if not valid:
        return {"reward_std": None, "reward_min": None, "reward_max": None, "length_std": None}
    rewards = np.array([e.reward for e in valid], dtype=float)
    lengths = np.array([e.episode_length for e in valid], dtype=float)
    return {
        "reward_std": round(float(rewards.std()), 6),
        "reward_min": round(float(rewards.min()), 6),
        "reward_max": round(float(rewards.max()), 6),
        "length_std": round(float(lengths.std()), 6),
    }
