"""User-supplied agents and environments: validated, stored, and loadable for inference.

Safety model (AGENTS.md: never execute untrusted code or unpickle untrusted data):

* **Agents** are accepted only as SB3 ``.zip`` archives or raw ``.pt`` state
  dicts. Weights are read with ``torch.load(weights_only=True)``, which refuses
  anything but tensors. The archive's pickled/cloudpickled members (``data``,
  optimizer state) are never deserialised - the architecture is inferred from
  the tensor shapes and then proven by loading the weights strictly into a real
  SB3 policy. ``.pkl``, ``.onnx`` and other formats are rejected with a reason.
* **Environments** are accepted only as declarative warehouse-grid layouts (JSON)
  that pass the same ``WarehouseConfig`` validation as built-in ones. Arbitrary
  environment code is not executed.

Uploaded artifacts live under ``<data_dir>/user_models`` and ``user_envs`` and
are addressed by content hash, so re-uploading identical bytes is a no-op.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
import os
import re
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gymnasium as gym
import numpy as np
from pydantic import ValidationError as PydanticValidationError

from backend.database.exceptions import (
    ConflictError,
    NotFoundError,
    StudioError,
    ValidationError,
)
from backend.environments.config import WarehouseConfig
from backend.environments.warehouse_env import Warehouse2DEnv

from . import envs as _envs
from .envs import ENVIRONMENTS, EnvDefinition, describe_space
from .params import ParamSpec

logger = logging.getLogger(__name__)

MODEL_PREFIX = "custom:"
ENV_PREFIX = "custom_env:"
MAX_MODEL_BYTES = 50 * 1024 * 1024
MAX_ZIP_MEMBERS = 32
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
MAX_PARAMETERS = 20_000_000
MAX_MODELS = 25
MAX_ENVS = 25
MAX_GRID = 20
ALLOWED_EXTENSIONS = (".zip", ".pt")
_MODEL_ID = re.compile(r"^mdl_[0-9a-f]{12}$")
_ENV_ID = re.compile(r"^env_[0-9a-f]{12}$")

_REJECTED_FORMATS = {
    ".pkl": "Pickle files can execute arbitrary code when loaded, so they are not accepted. Export the policy as an SB3 .zip or a .pt state dict instead.",
    ".pickle": "Pickle files can execute arbitrary code when loaded, so they are not accepted. Export the policy as an SB3 .zip or a .pt state dict instead.",
    ".onnx": "ONNX inference is not available in this deployment (no ONNX runtime is installed). Upload an SB3 .zip or a .pt state dict.",
}


class PayloadTooLarge(StudioError):
    error_code = "STUDIO-413"
    http_status = 413


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_dir() -> Path:
    from .session import data_dir

    return data_dir()


def models_dir() -> Path:
    return _data_dir() / "user_models"


def envs_dir() -> Path:
    return _data_dir() / "user_envs"


def incoming_dir() -> Path:
    return models_dir() / ".incoming"


def _fail(message: str, field: str = "file") -> ValidationError:
    return ValidationError(message, details={"errors": [{"field": field, "message": message}]})


def clean_name(raw: str | None, fallback: str) -> str:
    stem = re.sub(r"[^\w .()\-]", "", (raw or "").strip())[:60].strip()
    return stem or fallback


# --------------------------------------------------------------------------- #
# Weight inspection (no unpickling of untrusted objects)
# --------------------------------------------------------------------------- #


def _torch() -> Any:
    import torch

    return torch


def _layer_shapes(state: dict[str, Any], prefix: str) -> list[tuple[int, int]]:
    """(out, in) shapes of consecutive ``<prefix>.<i>.weight`` linear layers."""
    found: dict[int, tuple[int, int]] = {}
    pattern = re.compile(rf"^{re.escape(prefix)}\.(\d+)\.weight$")
    for key, tensor in state.items():
        match = pattern.match(key)
        if match:
            if tensor.ndim != 2:
                raise _fail(f"{key} is not a linear layer")
            found[int(match.group(1))] = (int(tensor.shape[0]), int(tensor.shape[1]))
    return [found[i] for i in sorted(found)]


def _chain(layers: list[tuple[int, int]], what: str) -> tuple[int, list[int]]:
    if not layers:
        raise _fail(f"The {what} network has no hidden layers; only MlpPolicy weights are supported")
    previous = layers[0][1]
    for out, inp in layers:
        if inp != previous:
            raise _fail(f"The {what} network layer sizes do not connect")
        previous = out
    return layers[0][1], [out for out, _ in layers]


def describe_state_dict(state: dict[str, Any], data_keys: set[str] | None) -> dict[str, Any]:
    """Infer family, algorithm, observation/action sizes and layer widths from tensors."""
    if "q_net.q_net.0.weight" in state:
        layers = _layer_shapes(state, "q_net.q_net")
        obs_dim, widths = _chain(layers, "Q")
        hidden, n_actions = widths[:-1], widths[-1]
        if not hidden:
            raise _fail("The Q network has no hidden layers; only MlpPolicy weights are supported")
        return {"family": "q", "algorithm": "DQN", "obs_dim": obs_dim, "action_type": "discrete", "action_dim": n_actions, "net_arch": hidden, "activation": "ReLU"}

    if "action_net.weight" in state and "value_net.weight" in state:
        obs_dim, pi = _chain(_layer_shapes(state, "mlp_extractor.policy_net"), "policy")
        vf_obs_dim, vf = _chain(_layer_shapes(state, "mlp_extractor.value_net"), "value")
        if vf_obs_dim != obs_dim:
            raise _fail("Policy and value networks disagree on the observation size")
        action_out = int(state["action_net.weight"].shape[0])
        if int(state["action_net.weight"].shape[1]) != pi[-1]:
            raise _fail("Action head does not match the policy network")
        if tuple(state["value_net.weight"].shape) != (1, vf[-1]):
            raise _fail("Value head does not match the value network")
        is_box = "log_std" in state
        if is_box and int(state["log_std"].shape[0]) != action_out:
            raise _fail("log_std does not match the action head")
        algorithm = "ActorCritic (PPO/A2C)"
        if data_keys is not None:
            # PPO stores clipping/epoch settings; A2C has no keys of its own, so it is the
            # remaining on-policy actor-critic. Weights alone cannot tell them apart.
            algorithm = "PPO" if {"n_epochs", "clip_range"} & data_keys else "A2C"
        return {"family": "actor_critic", "algorithm": algorithm, "obs_dim": obs_dim, "action_type": "box" if is_box else "discrete", "action_dim": action_out, "net_arch": {"pi": pi, "vf": vf}, "activation": "Tanh"}

    raise _fail("These weights are not a standard SB3 MlpPolicy (expected actor-critic or DQN tensors)")


def _validate_tensors(state: Any) -> dict[str, Any]:
    torch = _torch()
    if not isinstance(state, dict) or not state:
        raise _fail("The weights file does not contain a state dict")
    if len(state) > 200:
        raise _fail("The weights file contains too many tensors")
    total = 0
    for key, tensor in state.items():
        if not isinstance(key, str) or not isinstance(tensor, torch.Tensor):
            raise _fail("The weights file must contain only named tensors")
        if not tensor.is_floating_point() and tensor.dtype not in (torch.int64, torch.bool):
            raise _fail(f"Unsupported tensor type for {key}")
        if tensor.is_floating_point() and not bool(torch.isfinite(tensor).all()):
            raise _fail(f"{key} contains NaN or infinite values")
        total += tensor.numel()
        if total > MAX_PARAMETERS:
            raise _fail("The model has too many parameters for this studio")
    return state


def _load_state(path: Path, ext: str) -> tuple[dict[str, Any], set[str] | None]:
    torch = _torch()
    data_keys: set[str] | None = None
    try:
        if ext == ".zip":
            if not zipfile.is_zipfile(path):
                raise _fail("The file is not a valid ZIP archive")
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_ZIP_MEMBERS:
                    raise _fail("The archive contains too many files")
                if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
                    raise _fail("The archive expands to too much data")
                for info in infos:
                    name = info.filename
                    if name.startswith(("/", "\\")) or ".." in Path(name).parts or ":" in name:
                        raise _fail("The archive contains an unsafe path")
                names = {i.filename for i in infos}
                if "policy.pth" not in names or "data" not in names:
                    raise _fail("This is not a Stable-Baselines3 model archive (policy.pth and data are required)")
                try:
                    data_keys = set(json.loads(archive.read("data").decode("utf-8")))
                except (ValueError, UnicodeDecodeError):
                    raise _fail("The archive's data entry is not valid JSON") from None
                weights = archive.read("policy.pth")
            state = torch.load(io.BytesIO(weights), map_location="cpu", weights_only=True)
        else:
            state = torch.load(path, map_location="cpu", weights_only=True)
    except StudioError:
        raise
    except Exception:  # process boundary: unreadable or hostile file, reported generically
        logger.info("Rejected uploaded weights", exc_info=True)
        raise _fail("The weights could not be read safely. Only plain tensors are accepted; pickled objects are refused.") from None
    return _validate_tensors(state), data_keys


def _spaces(spec: dict[str, Any]) -> tuple[gym.Space, gym.Space]:
    obs = gym.spaces.Box(-np.inf, np.inf, shape=(int(spec["obs_dim"]),), dtype=np.float32)
    if spec["action_type"] == "discrete":
        return obs, gym.spaces.Discrete(int(spec["action_dim"]))
    return obs, gym.spaces.Box(-1.0, 1.0, shape=(int(spec["action_dim"]),), dtype=np.float32)


def build_policy(spec: dict[str, Any], observation_space: gym.Space, action_space: gym.Space) -> Any:
    """A real SB3 policy of the inferred architecture (weights not yet loaded)."""
    from stable_baselines3.common.policies import ActorCriticPolicy
    from stable_baselines3.dqn.policies import DQNPolicy

    torch = _torch()
    activation = torch.nn.ReLU if spec["activation"] == "ReLU" else torch.nn.Tanh
    schedule = lambda _progress: 1e-3  # only used to size the optimizer
    if spec["family"] == "q":
        return DQNPolicy(observation_space, action_space, schedule, net_arch=list(spec["net_arch"]), activation_fn=activation)
    return ActorCriticPolicy(observation_space, action_space, schedule, net_arch=dict(spec["net_arch"]), activation_fn=activation)


def inspect_weights_file(path: Path, ext: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate an uploaded file; returns (architecture spec, loaded state dict)."""
    state, data_keys = _load_state(path, ext)
    spec = describe_state_dict(state, data_keys)
    observation_space, action_space = _spaces(spec)
    try:
        build_policy(spec, observation_space, action_space).load_state_dict(state, strict=True)
    except (RuntimeError, ValueError, KeyError) as exc:
        logger.info("Weights do not fit the inferred architecture: %s", exc)
        raise _fail("The tensors do not form a complete, consistent SB3 policy") from None
    return spec, state


# --------------------------------------------------------------------------- #
# Model registry
# --------------------------------------------------------------------------- #


def is_custom_agent(key: Any) -> bool:
    return isinstance(key, str) and key.startswith(MODEL_PREFIX)


def _model_path(record: dict[str, Any]) -> Path:
    return models_dir() / record["model_id"] / record["stored_as"]


def _public(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k != "stored_as"}


def list_models() -> list[dict[str, Any]]:
    root = models_dir()
    records: list[dict[str, Any]] = []
    if root.is_dir():
        for meta in sorted(root.glob("mdl_*/meta.json")):
            try:
                records.append(json.loads(meta.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                logger.warning("Skipping unreadable model metadata %s", meta.parent.name)
    return sorted(records, key=lambda r: r["uploaded_at"], reverse=True)


def get_model(key_or_id: str) -> dict[str, Any]:
    model_id = key_or_id[len(MODEL_PREFIX):] if is_custom_agent(key_or_id) else key_or_id
    if not _MODEL_ID.match(model_id):
        raise NotFoundError("Model not found", details={"model_id": model_id[:40]})
    try:
        return json.loads((models_dir() / model_id / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise NotFoundError("Model not found", details={"model_id": model_id}) from None


def require_supported_extension(filename: str) -> str:
    """Fail fast (before reading the body) on formats that are refused."""
    ext = Path(filename).suffix.lower()
    if ext in _REJECTED_FORMATS:
        raise _fail(_REJECTED_FORMATS[ext])
    if ext not in ALLOWED_EXTENSIONS:
        raise _fail(f"Unsupported file type {ext or '(none)'}. Upload an SB3 .zip or a .pt state dict.")
    return ext


def store_model(temp_path: Path, filename: str, name: str | None) -> tuple[dict[str, Any], bool]:
    """Validate ``temp_path`` and move it into the registry. Returns (public record, was_duplicate)."""
    ext = require_supported_extension(filename)
    size = temp_path.stat().st_size
    if size == 0:
        raise _fail("The file is empty")
    sha = hashlib.sha256(temp_path.read_bytes()).hexdigest()
    model_id = f"mdl_{sha[:12]}"
    existing = models_dir() / model_id / "meta.json"
    if existing.exists():
        return _public(get_model(model_id)), True
    if len(list_models()) >= MAX_MODELS:
        raise ConflictError("Model library is full; delete a model first", details={"limit": MAX_MODELS})

    spec, _ = inspect_weights_file(temp_path, ext)
    stored_as = f"model{ext}"
    record = {
        "model_id": model_id,
        "key": f"{MODEL_PREFIX}{model_id}",
        "name": clean_name(name, clean_name(Path(filename).stem, "Uploaded model")),
        "original_filename": clean_name(Path(filename).name, "model"),
        "format": ext.lstrip("."),
        "sha256": sha,
        "size_bytes": size,
        "uploaded_at": _now(),
        "stored_as": stored_as,
        **spec,
        "activation_assumed": True,
        "algorithm_inferred": True,
    }
    directory = models_dir() / model_id
    directory.mkdir(parents=True, exist_ok=True)
    os.replace(temp_path, directory / stored_as)
    meta_tmp = directory / "meta.json.tmp"
    meta_tmp.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    os.replace(meta_tmp, directory / "meta.json")
    return _public(record), False


def delete_model(model_id: str) -> None:
    record = get_model(model_id)
    shutil.rmtree(models_dir() / record["model_id"], ignore_errors=True)


def new_incoming_path() -> Path:
    directory = incoming_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{uuid.uuid4().hex}.part"


def load_policy(record: dict[str, Any], observation_space: gym.Space, action_space: gym.Space) -> Any:
    """Re-verify the stored file, then build the policy against the real env spaces."""
    path = _model_path(record)
    try:
        data = path.read_bytes()
    except OSError:
        raise NotFoundError("The model file is missing", details={"model_id": record["model_id"]}) from None
    if hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise _fail("The stored model file no longer matches its recorded hash", field="agent")
    reason = incompatibility(record, describe_space(observation_space), describe_space(action_space), "this environment")
    if reason:
        raise _fail(reason, field="agent")
    spec, state = inspect_weights_file(path, "." + record["format"])
    policy = build_policy(spec, observation_space, action_space)
    policy.load_state_dict(state, strict=True)
    policy.set_training_mode(False)
    return policy


def incompatibility(record: dict[str, Any], obs: dict[str, Any], action: dict[str, Any], env_name: str) -> str | None:
    """Why ``record`` cannot act in an environment with these spaces, or None."""
    if obs.get("type") != "box":
        return f"{env_name} uses a {obs.get('type')} observation space; models need a flat Box observation."
    obs_dim = int(math.prod(obs["shape"]))
    if obs_dim != record["obs_dim"]:
        return f"This model expects {record['obs_dim']} observation values but {env_name} provides {obs_dim}."
    if action.get("type") != record["action_type"]:
        return f"This model outputs {record['action_type']} actions but {env_name} uses {action.get('type')} actions."
    size = int(action["n"]) if action["type"] == "discrete" else int(math.prod(action["shape"]))
    if size != record["action_dim"]:
        return f"This model has {record['action_dim']} action outputs but {env_name} needs {size}."
    return None


# --------------------------------------------------------------------------- #
# Custom environments (declarative warehouse layouts)
# --------------------------------------------------------------------------- #

_CUSTOM_ENV_PARAMS: tuple[ParamSpec, ...] = tuple(p for p in _envs.WAREHOUSE_PARAMS if p.key not in ("grid_size", "num_obstacles", "obstacle_movement", "layout_seed"))


def _cell(value: Any, field: str) -> tuple[int, int]:
    if not (isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in value)):
        raise _fail(f"{field} must be a [row, col] pair of integers", field)
    return int(value[0]), int(value[1])


def validate_layout(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise _fail("The layout must be a JSON object", "layout")
    unknown = set(raw) - {"name", "rows", "cols", "start", "goal", "obstacles", "description"}
    if unknown:
        raise _fail(f"Unknown layout fields: {sorted(unknown)}", "layout")
    rows, cols = raw.get("rows"), raw.get("cols")
    for label, value in (("rows", rows), ("cols", cols)):
        if not isinstance(value, int) or isinstance(value, bool) or not 2 <= value <= MAX_GRID:
            raise _fail(f"{label} must be an integer between 2 and {MAX_GRID}", label)
    obstacles = raw.get("obstacles", [])
    if not isinstance(obstacles, list) or len(obstacles) > rows * cols:
        raise _fail("obstacles must be a list of [row, col] cells", "obstacles")
    layout = {
        "rows": rows,
        "cols": cols,
        "start": list(_cell(raw.get("start"), "start")),
        "goal": list(_cell(raw.get("goal"), "goal")),
        "obstacles": sorted({_cell(o, "obstacles") for o in obstacles}),
    }
    layout["obstacles"] = [list(o) for o in layout["obstacles"]]
    try:
        WarehouseConfig(**layout, max_episode_steps=100, goal_reward=1.0, collision_penalty=0.0)
    except (PydanticValidationError, ValueError) as exc:
        details = exc.errors() if hasattr(exc, "errors") else [{"msg": str(exc)}]
        message = "; ".join(
            str(e.get("msg", e)).removeprefix("Value error, ") for e in details
        )
        raise _fail(message[:300], "layout") from None
    return layout


def store_environment(raw: Any) -> tuple[dict[str, Any], bool]:
    layout = validate_layout(raw)
    name = clean_name(raw.get("name") if isinstance(raw, dict) else None, f"Custom grid {layout['rows']}x{layout['cols']}")
    canonical = json.dumps(layout, sort_keys=True)
    env_id = f"env_{hashlib.sha256(canonical.encode()).hexdigest()[:12]}"
    path = envs_dir() / f"{env_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), True
    if len(list_environments()) >= MAX_ENVS:
        raise ConflictError("Environment library is full; delete one first", details={"limit": MAX_ENVS})
    record = {"env_id": env_id, "key": f"{ENV_PREFIX}{env_id}", "name": name, "layout": layout, "uploaded_at": _now()}
    envs_dir().mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    return record, False


def list_environments() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if envs_dir().is_dir():
        for path in sorted(envs_dir().glob("env_*.json")):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                logger.warning("Skipping unreadable environment %s", path.name)
    return sorted(records, key=lambda r: r["uploaded_at"], reverse=True)


def get_environment_record(key_or_id: str) -> dict[str, Any]:
    env_id = key_or_id.removeprefix(ENV_PREFIX)
    if not _ENV_ID.match(env_id):
        raise NotFoundError("Environment not found", details={"env_id": env_id[:40]})
    try:
        return json.loads((envs_dir() / f"{env_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise NotFoundError("Environment not found", details={"env_id": env_id}) from None


def delete_environment(env_id: str) -> None:
    record = get_environment_record(env_id)
    (envs_dir() / f"{record['env_id']}.json").unlink(missing_ok=True)


def _definition_for(record: dict[str, Any]) -> EnvDefinition:
    layout = record["layout"]

    def make(params: dict[str, Any], seed: int) -> gym.Env:
        config = WarehouseConfig(
            environment_id="custom_warehouse",
            environment_version="custom_warehouse_v1",
            rows=layout["rows"],
            cols=layout["cols"],
            start=tuple(layout["start"]),
            goal=tuple(layout["goal"]),
            obstacles=[tuple(o) for o in layout["obstacles"]],
            max_episode_steps=int(params["max_episode_steps"]),
            goal_reward=float(params["goal_reward"]),
            step_reward=float(params["step_reward"]),
            collision_penalty=float(params["collision_penalty"]),
            collision_reward=bool(params["collision_ends_episode"]),
        )
        return Warehouse2DEnv(config)

    return EnvDefinition(
        key=record["key"],
        name=record["name"],
        description=f"Your uploaded {layout['rows']}x{layout['cols']} warehouse grid with {len(layout['obstacles'])} obstacles.",
        dimension="3D",
        difficulty="Custom",
        renderer="grid_maze",
        params=_CUSTOM_ENV_PARAMS,
        make=make,
        scene=_envs._warehouse_scene,
        frame_state=_envs._warehouse_state,
        classify=_envs._warehouse_classify,
        chaos_kinds=_envs.WAREHOUSE_CHAOS_KINDS,
        noise_scale=_envs.WAREHOUSE_NOISE_SCALE,
    )


def resolve_environment(key: Any) -> EnvDefinition | None:
    """Built-in or uploaded environment definition for ``key``; None if unknown."""
    if isinstance(key, str) and key in ENVIRONMENTS:
        return ENVIRONMENTS[key]
    if isinstance(key, str) and key.startswith(ENV_PREFIX):
        try:
            return _definition_for(get_environment_record(key))
        except NotFoundError:
            return None
    return None


def all_environments() -> list[EnvDefinition]:
    return [*ENVIRONMENTS.values(), *(_definition_for(r) for r in list_environments())]
