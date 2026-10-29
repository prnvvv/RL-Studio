"""Stable fingerprint helpers for configs, agent definitions, and runs.

A *fingerprint* is a short, deterministic hash of a canonicalized view of an
object.  Fingerprints let provenance (Person 4) bind a checkpoint or evaluation
to the exact environment/agent/run it was produced under, without storing the
whole object in every record.

Normalization rules (documented, AGENTS.md §10):
- Mapping keys are sorted; obstacle/cell lists are sorted by (row, col).
- Floats are rounded to 12 decimal places to absorb binary noise.
- NaN/inf values raise (they are not valid config values).
- JSON is encoded with fixed separators so byte output is reproducible.
- The digest is SHA-256, lower-hex, 16 hex characters.

These are intentionally pure functions with no I/O or RNG.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

_ROUND = 12
_DIGEST_LEN = 16


def _normalize(value: Any) -> Any:
    """Recursively produce a canonical, JSON-safe representation."""
    if isinstance(value, dict):
        return {k: _normalize(value[k]) for k in sorted(value, key=lambda x: str(x))}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        rounded = round(value, _ROUND)
        if not math.isfinite(rounded):
            raise ValueError("fingerprint input contains NaN or inf; a valid config must be finite")
        return rounded
    if isinstance(value, (int, str)) or value is None:
        return value
    return str(value)


def canonical_json(obj: Any) -> str:
    """Return deterministic JSON for ``obj`` (sorted keys, fixed separators)."""
    return json.dumps(_normalize(obj), sort_keys=True, separators=(",", ":"))


def sha256_hex(data: bytes | str) -> str:
    """Return the full SHA-256 hex digest of ``data``."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def short_hash(data: bytes | str) -> str:
    """Return a fixed-length (``_DIGEST_LEN``) prefix of the SHA-256 digest."""
    return sha256_hex(data)[:_DIGEST_LEN]


def config_fingerprint(config: Any) -> str:
    """Stable fingerprint for a :class:`WarehouseConfig` (or its dict form).

    Accepts a :class:`WarehouseConfig` instance or a plain dict.  The canonical
    form excludes per-run transient fields (seeds, counters) — those belong in
    the *run* fingerprint, not the environment fingerprint.
    """
    if hasattr(config, "default_fingerprint_inputs"):
        payload = config.default_fingerprint_inputs()
    elif hasattr(config, "model_dump"):
        payload = config.model_dump()
    else:
        payload = config
    return short_hash(canonical_json(payload))


def agent_fingerprint(algorithm: str, hyperparameters: dict, extra: dict | None = None) -> str:
    """Stable fingerprint for an agent (algorithm + hyperparameters).

    ``extra`` may carry observation/reward-normalization settings, optimizer
    state policy, etc.  All inputs are canonicalized.
    """
    payload: dict[str, Any] = {"algorithm": algorithm, "hyperparameters": dict(hyperparameters)}
    if extra:
        payload["extra"] = dict(extra)
    return short_hash(canonical_json(payload))


def run_fingerprint(
    *,
    config_fingerprint: str,
    agent_fingerprint: str,
    seed: int,
    training_update_budget: int | None = None,
    extra: dict | None = None,
) -> str:
    """Stable fingerprint for a training run.

    Bundles environment and agent fingerprints with the seed and budget so two
    runs that differ only in seed get distinct run fingerprints.
    """
    payload: dict[str, Any] = {
        "config": config_fingerprint,
        "agent": agent_fingerprint,
        "seed": int(seed),
    }
    if training_update_budget is not None:
        payload["budget"] = int(training_update_budget)
    if extra:
        payload["extra"] = dict(extra)
    return short_hash(canonical_json(payload))
