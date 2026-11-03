"""Agent templates and the capability catalog served to the studio UI.

Only algorithms that import and run in this deployment are listed, and
compatibility is derived from each environment's real action space rather than
hand-maintained tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import gymnasium as gym
import numpy as np

from . import custom
from .envs import ENVIRONMENTS, EnvDefinition, describe_space, unavailable_reason
from .params import ParamSpec

NET_ARCHES: dict[str, list[int]] = {
    "small (32x32)": [32, 32],
    "medium (64x64)": [64, 64],
    "large (128x128)": [128, 128],
    "xl (256x256)": [256, 256],
}
_ARCH_OPTIONS = tuple(NET_ARCHES)


@dataclass(frozen=True)
class AgentDefinition:
    key: str
    name: str
    description: str
    family: str  # "on-policy" | "off-policy"
    action_spaces: tuple[str, ...]  # supported action space types
    params: tuple[ParamSpec, ...]
    reported_metrics: tuple[str, ...]
    #: SB3 policy class name passed to the algorithm.
    policy: str = "MlpPolicy"
    #: Whether the live action-probability ("brain") view can read this policy.
    supports_brain: bool = True
    #: Whether a human can take over the agent (needs a feed-forward policy and discrete control).
    supports_manual: bool = True


_ARCH = ParamSpec("net_arch", "Network architecture", "choice", "medium (64x64)", "Hidden layers of the policy/value MLP.", options=_ARCH_OPTIONS)

AGENTS: dict[str, AgentDefinition] = {
    "PPO": AgentDefinition(
        key="PPO",
        name="PPO",
        description="Proximal Policy Optimization. Clipped on-policy updates; a robust default.",
        family="on-policy",
        action_spaces=("discrete", "box"),
        params=(
            ParamSpec("learning_rate", "Learning rate", "float", 3e-4, "Optimizer step size.", 1e-6, 1e-1, 1e-5),
            ParamSpec("gamma", "Gamma", "float", 0.99, "Discount factor.", 0.8, 0.9999, 0.001),
            ParamSpec("n_steps", "Steps per update", "int", 512, "Rollout length before each update.", 16, 8192, 16),
            ParamSpec("batch_size", "Batch size", "int", 64, "Minibatch size; must not exceed steps per update.", 8, 2048, 8),
            ParamSpec("n_epochs", "Epochs", "int", 10, "Optimisation epochs per update.", 1, 50, 1),
            ParamSpec("ent_coef", "Entropy coefficient", "float", 0.0, "Exploration bonus weight.", 0.0, 0.1, 0.001),
            ParamSpec("clip_range", "Clip range", "float", 0.2, "PPO policy clipping range.", 0.05, 0.5, 0.01),
            ParamSpec("gae_lambda", "GAE lambda", "float", 0.95, "Advantage estimator smoothing.", 0.8, 1.0, 0.01),
            _ARCH,
        ),
        reported_metrics=("policy_loss", "value_loss", "entropy", "approx_kl", "explained_variance", "clip_fraction"),
    ),
    "A2C": AgentDefinition(
        key="A2C",
        name="A2C",
        description="Advantage Actor-Critic. Synchronous on-policy updates with short rollouts.",
        family="on-policy",
        action_spaces=("discrete", "box"),
        params=(
            ParamSpec("learning_rate", "Learning rate", "float", 7e-4, "Optimizer step size.", 1e-6, 1e-1, 1e-5),
            ParamSpec("gamma", "Gamma", "float", 0.99, "Discount factor.", 0.8, 0.9999, 0.001),
            ParamSpec("n_steps", "Steps per update", "int", 16, "Rollout length before each update.", 1, 2048, 1),
            ParamSpec("ent_coef", "Entropy coefficient", "float", 0.0, "Exploration bonus weight.", 0.0, 0.1, 0.001),
            ParamSpec("vf_coef", "Value loss weight", "float", 0.5, "Weight of the value loss.", 0.0, 2.0, 0.05),
            ParamSpec("gae_lambda", "GAE lambda", "float", 1.0, "Advantage estimator smoothing.", 0.8, 1.0, 0.01),
            _ARCH,
        ),
        reported_metrics=("policy_loss", "value_loss", "entropy", "explained_variance"),
    ),
    "DQN": AgentDefinition(
        key="DQN",
        name="DQN",
        description="Deep Q-Network. Off-policy value learning with a replay buffer; discrete actions only.",
        family="off-policy",
        action_spaces=("discrete",),
        params=(
            ParamSpec("learning_rate", "Learning rate", "float", 1e-3, "Optimizer step size.", 1e-6, 1e-1, 1e-5),
            ParamSpec("gamma", "Gamma", "float", 0.99, "Discount factor.", 0.8, 0.9999, 0.001),
            ParamSpec("batch_size", "Batch size", "int", 64, "Replay minibatch size.", 8, 1024, 8),
            ParamSpec("buffer_size", "Replay buffer", "int", 50_000, "Transitions kept for replay.", 1000, 1_000_000, 1000),
            ParamSpec("learning_starts", "Learning starts", "int", 1000, "Steps collected before learning begins.", 0, 100_000, 100),
            ParamSpec("train_freq", "Train frequency", "int", 4, "Environment steps between updates.", 1, 64, 1),
            ParamSpec("target_update_interval", "Target update", "int", 250, "Steps between target network syncs.", 1, 10_000, 10),
            ParamSpec("exploration_fraction", "Exploration fraction", "float", 0.3, "Share of training spent annealing epsilon.", 0.01, 1.0, 0.01),
            ParamSpec("exploration_final_eps", "Final epsilon", "float", 0.05, "Epsilon after annealing.", 0.0, 1.0, 0.01),
            _ARCH,
        ),
        reported_metrics=("loss", "exploration_rate"),
    ),
    "SAC": AgentDefinition(
        key="SAC",
        name="SAC",
        description="Soft Actor-Critic. Off-policy maximum-entropy learning for continuous (Box) actions.",
        family="off-policy",
        action_spaces=("box",),
        params=(
            ParamSpec("learning_rate", "Learning rate", "float", 3e-4, "Optimizer step size.", 1e-6, 1e-1, 1e-5),
            ParamSpec("gamma", "Gamma", "float", 0.99, "Discount factor.", 0.8, 0.9999, 0.001),
            ParamSpec("batch_size", "Batch size", "int", 256, "Replay minibatch size.", 8, 2048, 8),
            ParamSpec("buffer_size", "Replay buffer", "int", 100_000, "Transitions kept for replay.", 1000, 1_000_000, 1000),
            ParamSpec("learning_starts", "Learning starts", "int", 1000, "Steps collected before learning begins.", 0, 100_000, 100),
            ParamSpec("tau", "Target smoothing (tau)", "float", 0.005, "Soft-update rate of the target networks.", 0.0005, 1.0, 0.0005),
            ParamSpec("train_freq", "Train frequency", "int", 1, "Environment steps between updates.", 1, 64, 1),
            ParamSpec("gradient_steps", "Gradient steps", "int", 1, "Gradient updates per training call.", 1, 64, 1),
            _ARCH,
        ),
        reported_metrics=("actor_loss", "critic_loss", "ent_coef", "ent_coef_loss"),
        supports_brain=False,
        supports_manual=False,
    ),
    "TD3": AgentDefinition(
        key="TD3",
        name="TD3",
        description="Twin Delayed DDPG. Off-policy deterministic actor-critic for continuous (Box) actions.",
        family="off-policy",
        action_spaces=("box",),
        params=(
            ParamSpec("learning_rate", "Learning rate", "float", 1e-3, "Optimizer step size.", 1e-6, 1e-1, 1e-5),
            ParamSpec("gamma", "Gamma", "float", 0.99, "Discount factor.", 0.8, 0.9999, 0.001),
            ParamSpec("batch_size", "Batch size", "int", 256, "Replay minibatch size.", 8, 2048, 8),
            ParamSpec("buffer_size", "Replay buffer", "int", 100_000, "Transitions kept for replay.", 1000, 1_000_000, 1000),
            ParamSpec("learning_starts", "Learning starts", "int", 1000, "Steps collected before learning begins.", 0, 100_000, 100),
            ParamSpec("tau", "Target smoothing (tau)", "float", 0.005, "Soft-update rate of the target networks.", 0.0005, 1.0, 0.0005),
            ParamSpec("train_freq", "Train frequency", "int", 1, "Environment steps between updates.", 1, 64, 1),
            ParamSpec("gradient_steps", "Gradient steps", "int", 1, "Gradient updates per training call.", 1, 64, 1),
            ParamSpec("policy_delay", "Policy delay", "int", 2, "Critic updates per actor update.", 1, 16, 1),
            ParamSpec("exploration_noise", "Exploration noise", "float", 0.1, "Std of the Gaussian noise added to actions while training (TD3 is deterministic otherwise).", 0.0, 1.0, 0.01),
            _ARCH,
        ),
        reported_metrics=("actor_loss", "critic_loss"),
        supports_brain=False,
        supports_manual=False,
    ),
    "PPO_LSTM": AgentDefinition(
        key="PPO_LSTM",
        name="PPO-LSTM",
        description="PPO with an LSTM policy (sb3-contrib RecurrentPPO). On-policy; the recurrent state gives it memory.",
        family="on-policy",
        action_spaces=("discrete", "box"),
        params=(
            ParamSpec("learning_rate", "Learning rate", "float", 3e-4, "Optimizer step size.", 1e-6, 1e-1, 1e-5),
            ParamSpec("gamma", "Gamma", "float", 0.99, "Discount factor.", 0.8, 0.9999, 0.001),
            ParamSpec("n_steps", "Steps per update", "int", 128, "Rollout length before each update.", 16, 8192, 16),
            ParamSpec("batch_size", "Batch size", "int", 128, "Minibatch size; must not exceed steps per update.", 8, 2048, 8),
            ParamSpec("n_epochs", "Epochs", "int", 10, "Optimisation epochs per update.", 1, 50, 1),
            ParamSpec("ent_coef", "Entropy coefficient", "float", 0.0, "Exploration bonus weight.", 0.0, 0.1, 0.001),
            ParamSpec("clip_range", "Clip range", "float", 0.2, "PPO policy clipping range.", 0.05, 0.5, 0.01),
            ParamSpec("gae_lambda", "GAE lambda", "float", 0.95, "Advantage estimator smoothing.", 0.8, 1.0, 0.01),
            ParamSpec("lstm_hidden_size", "LSTM hidden size", "int", 64, "Units in the recurrent layer.", 8, 512, 8),
        ),
        reported_metrics=("policy_loss", "value_loss", "entropy", "approx_kl", "explained_variance", "clip_fraction"),
        policy="MlpLstmPolicy",
        supports_brain=False,
        supports_manual=False,
    ),
}

SB3_NAMES = {"PPO": "PPO", "A2C": "A2C", "DQN": "DQN", "SAC": "SAC", "TD3": "TD3", "PPO_LSTM": "RecurrentPPO"}
#: Algorithms that live in sb3-contrib rather than stable-baselines3.
CONTRIB = {"PPO_LSTM"}
RECURRENT = {"PPO_LSTM"}
OFF_POLICY_REPLAY = {"DQN", "SAC", "TD3"}


def sb3_class(key: str) -> Any:
    if key in CONTRIB:
        import sb3_contrib

        return getattr(sb3_contrib, SB3_NAMES[key])
    import stable_baselines3 as sb3

    return getattr(sb3, SB3_NAMES[key])


def build_model(agent_key: str, venv: Any, agent_params: dict[str, Any], *, seed: int, device: str) -> tuple[Any, dict[str, Any]]:
    """Create the real SB3 model for an agent and report how it was configured."""
    definition = AGENTS[agent_key]
    params = dict(agent_params)
    policy_kwargs: dict[str, Any] = {}
    if "net_arch" in params:
        policy_kwargs["net_arch"] = NET_ARCHES[params.pop("net_arch")]
    if "lstm_hidden_size" in params:
        policy_kwargs["lstm_hidden_size"] = int(params.pop("lstm_hidden_size"))
        policy_kwargs["n_lstm_layers"] = 1
    noise = params.pop("exploration_noise", None)
    if noise is not None and float(noise) > 0:
        from stable_baselines3.common.noise import NormalActionNoise

        size = int(np.prod(venv.action_space.shape))
        params["action_noise"] = NormalActionNoise(mean=np.zeros(size), sigma=np.full(size, float(noise)))
    # SB3 mutates the policy_kwargs it is given (A2C inserts its optimizer class), so it gets a copy
    # and only the settings chosen here are reported back (they must stay JSON-serialisable).
    model = sb3_class(agent_key)(definition.policy, venv, seed=seed, device=device, policy_kwargs=dict(policy_kwargs), verbose=0, **params)
    return model, {"policy": definition.policy, **policy_kwargs}


def available_agents() -> dict[str, AgentDefinition]:
    """Agents whose implementation can actually be imported here."""
    available: dict[str, AgentDefinition] = {}
    for key, definition in AGENTS.items():
        try:
            sb3_class(key)
        except (ImportError, AttributeError):
            continue  # e.g. sb3-contrib not installed: the agent is simply not offered
        available[key] = definition
    return available


def action_space_type(space: gym.Space) -> str:
    return describe_space(space)["type"]


def compatible(agent: AgentDefinition, env_action_type: str) -> bool:
    return env_action_type in agent.action_spaces


def devices() -> list[str]:
    found = ["cpu"]
    try:
        import torch

        if torch.cuda.is_available():
            found.append("cuda")
    except ImportError:  # pragma: no cover
        pass
    return found


TRAINING_PARAMS: tuple[ParamSpec, ...] = (
    ParamSpec("total_timesteps", "Total timesteps", "int", 20_000, "Environment steps to train for.", 1000, 1_000_000, 1000),
    ParamSpec("seed", "Training seed", "int", 0, "Seeds the algorithm and environment.", 0, 2**31 - 1, 1),
    ParamSpec("simulation_speed", "Simulation speed", "float", 4.0, "Playback pacing only (0 = unthrottled). Does not change learning.", 0.0, 64.0, 0.25),
    ParamSpec("checkpoint_every", "Checkpoint every", "int", 5000, "Timesteps between checkpoints (0 = off).", 0, 1_000_000, 500),
    ParamSpec("eval_every", "Evaluate every", "int", 5000, "Timesteps between evaluations (0 = off).", 0, 1_000_000, 500),
    ParamSpec("eval_episodes", "Evaluation episodes", "int", 5, "Deterministic episodes per evaluation.", 1, 50, 1),
    ParamSpec("device", "Device", "choice", "cpu", "Compute device.", options=tuple(devices())),
)


def _env_entry(definition: EnvDefinition, agents: dict[str, AgentDefinition]) -> dict[str, Any]:
    defaults = {spec.key: spec.default for spec in definition.params}
    unavailable = unavailable_reason(definition)
    if unavailable is None:
        probe = definition.make(defaults, 0)
        try:
            obs_space = describe_space(probe.observation_space)
            act_space = describe_space(probe.action_space)
            scene = definition.scene(defaults, probe)
        finally:
            probe.close()
    else:
        # Shown, but disabled: the UI explains what is missing instead of hiding the environment.
        obs_space, act_space, scene = {"type": "unknown"}, {"type": "unknown"}, {}
    is_custom = definition.key not in ENVIRONMENTS
    return {
        "key": definition.key,
        "kind": "custom" if is_custom else "builtin",
        "name": definition.name,
        "description": definition.description,
        "dimension": definition.dimension,
        "difficulty": definition.difficulty,
        "renderer": definition.renderer,
        "observation_space": obs_space,
        "action_space": act_space,
        "default_scene": scene,
        "supports_disturbances": definition.disturbances,
        "chaos_kinds": list(definition.chaos_kinds),
        "manual": definition.manual,
        "available": unavailable is None,
        "unavailable_reason": unavailable,
        "params": [spec.to_dict() for spec in definition.params],
        "compatible_agents": [k for k, a in agents.items() if compatible(a, act_space["type"])],
    }


def _custom_agent_entries(environments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Uploaded models, with compatibility derived from each environment's real spaces."""
    entries: list[dict[str, Any]] = []
    for record in custom.list_models():
        compatible = [
            e["key"]
            for e in environments
            if custom.incompatibility(record, e["observation_space"], e["action_space"], e["name"]) is None
        ]
        for env in environments:
            if env["key"] in compatible:
                env["compatible_agents"].append(record["key"])
        entries.append(
            {
                "key": record["key"],
                "kind": "custom",
                "name": record["name"],
                "description": f"Uploaded {record['format']} policy ({record['algorithm']}). Runs inference only; it does not learn.",
                "family": "custom",
                "action_spaces": [record["action_type"]],
                "params": [],
                "reported_metrics": [],
                "compatible_environments": compatible,
                "custom": {k: v for k, v in record.items() if k not in ("stored_as", "key")},
            }
        )
    return entries


def build_catalog() -> dict[str, Any]:
    agents = available_agents()
    environments = [_env_entry(d, agents) for d in custom.all_environments()]
    for entry in environments:
        if entry["kind"] == "custom":
            record = custom.get_environment_record(entry["key"])
            entry["custom"] = {"env_id": record["env_id"], "uploaded_at": record["uploaded_at"], "layout": record["layout"]}
    env_by_key = {e["key"]: e for e in environments}
    custom_agents = _custom_agent_entries(environments)
    return {
        "schema_version": "1.1",
        "limits": {
            "model_extensions": list(custom.ALLOWED_EXTENSIONS),
            "max_model_bytes": custom.MAX_MODEL_BYTES,
            "max_grid": custom.MAX_GRID,
        },
        "agents": [
            {
                "key": a.key,
                "kind": "builtin",
                "name": a.name,
                "description": a.description,
                "family": a.family,
                "action_spaces": list(a.action_spaces),
                "params": [p.to_dict() for p in a.params],
                "reported_metrics": list(a.reported_metrics),
                "supports_brain": a.supports_brain,
                "supports_manual": a.supports_manual,
                "compatible_environments": [
                    k for k, e in env_by_key.items() if a.key in e["compatible_agents"]
                ],
            }
            for a in agents.values()
        ]
        + custom_agents,
        "environments": environments,
        "training_params": [p.to_dict() for p in TRAINING_PARAMS],
        "net_arches": list(NET_ARCHES),
    }
