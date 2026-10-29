"""Schema normalisation for the verification subsystem's input layer.

Normalises supported dictionary / Pydantic-model inputs into the canonical
structures expected by the existing verification models.  Only safe, documented
normalisations are applied — missing-field / null / empty / invalid distinctions
are preserved where they matter.  Unknown configuration fields are preserved
through the ``extra = \"allow\"`` mechanism used by the canonical models.

Do not invent defaults that change agent behaviour, environment behaviour,
training settings, or developer intent.  Do not silently coerce invalid values
into valid-looking values.  Do not infer requirements, diagnose faults, calculate
anomaly scores, or make verification decisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


from backend.verification.exceptions import InputValidationError


# ---------------------------------------------------------------------------
# Helper: parse an optional string that may be None, empty, or whitespace-only
# ---------------------------------------------------------------------------

def _normalize_optional_string(
    value: Any,
) -> Optional[str]:
    """Return *value* as ``Optional[str]``.

    - ``None``  → ``None``
    - ``""``    → ``None``  (empty string treated as missing)
    - Whitespace-only → ``None``
    - Anything else → ``str(value)``
    """
    if value is None:
        return None
    if isinstance(value, str):
        if value.strip() == "":
            return None
        return value
    # Non-string, non-None: convert and strip
    s = str(value).strip()
    return s if s != "" else None


# ---------------------------------------------------------------------------
# Helper: normalise a timestamp string / datetime into a timezone-aware UTC
# datetime, or None.  Invalid timestamps raise InputValidationError.
# ---------------------------------------------------------------------------

def _normalize_timestamp(
    value: Any,
) -> Optional[datetime]:
    """Return *value* as a timezone-aware UTC ``datetime``, or ``None``.

    - ``None``  → ``None``
    - ``datetime`` → ensured timezone-aware in UTC
    - ``str``    → parsed via ``fromisoformat``; must be ISO-8601
    - Everything else → ``None`` (preserves "missing" semantics)
    Invalid ISO strings raise ``InputValidationError``.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
            return parsed
        except (ValueError, TypeError) as exc:
            raise InputValidationError(
                f"Invalid ISO-8601 timestamp: {value!r}"
            ) from exc
    # Non-supported type: return None to preserve "missing" semantics
    return None


# ---------------------------------------------------------------------------
# 1. Normalise agent-related sub-dictionaries
# ---------------------------------------------------------------------------


def normalise_agent_metadata(
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalise a agent metadata dictionary into the shape expected by
    ``AgentMetadata``.

    - Known keys are passed through (agent_id, agent_type, agent_template,
      template_version, configuration_fingerprint, extensions).
    - Unknown keys are preserved in ``extensions`` so they do not cause
      validation errors.
    - Missing fields are simply omitted; the canonical models use
      ``default_factory`` or ``Optional`` to handle absence.
    """
    if not isinstance(data, dict):
        return {"extensions": data if isinstance(data, dict) else {"_raw": str(data)}}

    result: Dict[str, Any] = {}
    # Only include keys that are present; absent keys let the model use
    # its default factory (e.g. agent_id UUID generation).
    if "agent_id" in data:
        result["agent_id"] = data["agent_id"]
    if "agent_type" in data:
        result["agent_type"] = data["agent_type"]
    if "agent_template" in data:
        result["agent_template"] = data["agent_template"]
    if "template_version" in data:
        result["template_version"] = data["template_version"]
    if "configuration_fingerprint" in data:
        result["configuration_fingerprint"] = data["configuration_fingerprint"]
    # Extensions always present (may be empty dict)
    result["extensions"] = dict(data.get("extensions", {}))

    # Any key not explicitly extracted goes into extensions
    known_keys = {
        "agent_id",
        "agent_type",
        "agent_template",
        "template_version",
        "configuration_fingerprint",
        "extensions",
    }
    extra_keys = set(data.keys()) - known_keys
    if extra_keys:
        result["extensions"].update({k: data[k] for k in extra_keys})

    return result


# ---------------------------------------------------------------------------
# 2. Normalise environment configuration
# ---------------------------------------------------------------------------


def normalise_environment_config(
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalise an environment configuration dictionary.

    - Known keys are passed through.
    - Unknown keys are preserved in the result dict (they will be accepted
      by the canonical model via ``extra = \"allow\"``).
    - Empty / null values become ``None``.
    - ``extensions`` key is preserved and merged with any extra unknown keys.
    """
    if not isinstance(data, dict):
        return {"extensions": data if isinstance(data, dict) else {"_raw": str(data)}}

    result: Dict[str, Any] = {}

    # Pass through all keys from the source dict
    for key, value in data.items():
        if key == "extensions":
            # Extensions are accumulated separately; we'll merge at the end
            continue
        # Preserve value as-is; None / empty become None naturally
        result[key] = value

    # Ensure extensions dict exists
    result["extensions"] = dict(data.get("extensions", {}))

    return result


# ---------------------------------------------------------------------------
# 3. Normalise training configuration
# ---------------------------------------------------------------------------


def normalise_training_config(
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalise a training configuration dictionary.

    - Known hyper-parameter keys are passed through.
    - Unknown keys are preserved in the result dict (they will be accepted
      by the canonical model via ``extra = \"allow\"``).
    - Empty / null values become ``None``.
    - ``extensions`` key is preserved and merged with any extra unknown keys.
    """
    if not isinstance(data, dict):
        return {"extensions": data if isinstance(data, dict) else {"_raw": str(data)}}

    result: Dict[str, Any] = {}

    # Pass through all keys from the source dict
    for key, value in data.items():
        if key == "extensions":
            # Extensions are accumulated separately; we'll merge at the end
            continue
        # Preserve value as-is; None / empty become None naturally
        result[key] = value

    # Ensure extensions dict exists
    result["extensions"] = dict(data.get("extensions", {}))

    return result


# ---------------------------------------------------------------------------
# 4. Normalise developer intent
# ---------------------------------------------------------------------------


def normalise_developer_intent(
    data: Any,
) -> Optional[str]:
    """Normalise developer intent into an ``Optional[str]``.

    - ``None``  → ``None``
    - ``str``   → stripped; empty/whitespace-only → ``None``
    - Other types → converted to string, stripped; empty → ``None``
    """
    if data is None:
        return None
    if isinstance(data, str):
        stripped = data.strip()
        return stripped if stripped != "" else None
    # Non-string: try to coerce to string safely
    try:
        s = str(data).strip()
        return s if s != "" else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 5. Normalise execution evidence
# ---------------------------------------------------------------------------


def normalise_execution_evidence(
    data: Any,
) -> Optional[Dict[str, Any]]:
    """Normalise execution evidence into an optional dictionary.

    - ``None``  → ``None``  (no evidence)
    - ``dict``  → returned as-is (unknown keys preserved via extensions policy)
    - Other types → converted to dict if possible, otherwise ``None``

    The canonical model expects ``Optional[Dict[str, Any]]`` and uses
    ``extra = "allow```` to preserve arbitrary evidence payloads without
    treating them as requirements.
    """
    if data is None:
        return None
    if isinstance(data, dict):
        return dict(data)
    # Attempt safe conversion
    try:
        if isinstance(data, (list, tuple)):
            # Convert list of items to a simple dict marker
            return {"_items": [str(v) for v in data]}
        return {"_raw": str(data)}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 6. Top-level normalise function: map raw input dict → VerificationInput fields
# ---------------------------------------------------------------------------


def normalise_verification_input(
    raw: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalise a raw input dictionary into a flat dict of fields ready for
    ``VerificationInput`` construction.

    The returned dictionary keys match the field names of
    ``backend.verification.models.VerificationInput`` so they can be
    directly unpacked (e.g. ``VerificationInput(**normalised)``).

    Supported top-level keys in *raw*:
    - ``agent_metadata``                → normalised via ``normalise_agent_metadata``
    - ``environment_config``            → normalised via ``normalise_environment_config``
    - ``training_config``               → normalised via ``normalise_training_config``
    - ``developer_intent``              → normalised via ``normalise_developer_intent``
    - ``execution_evidence``            → normalised via ``normalise_execution_evidence``
    - Any other keys are preserved in the ``extensions`` sub-dict.
    """
    if not isinstance(raw, dict):
        raise InputValidationError(
            "Verification input must be a dictionary"
        )

    # Start with extensions so any truly unknown keys have a home
    normalised: Dict[str, Any] = {"extensions": {}}

    # Agent metadata
    agent_meta = raw.get("agent_metadata")
    if agent_meta is not None:
        normalised["agent_metadata"] = normalise_agent_metadata(agent_meta)

    # Environment config
    env_config = raw.get("environment_config")
    if env_config is not None:
        normalised["environment_config"] = normalise_environment_config(env_config)

    # Training config
    training_config = raw.get("training_config")
    if training_config is not None:
        normalised["training_config"] = normalise_training_config(training_config)

    # Developer intent
    dev_intent = raw.get("developer_intent")
    normalised["developer_intent"] = normalise_developer_intent(dev_intent)

    # Execution evidence
    exec_evidence = raw.get("execution_evidence")
    normalised["execution_evidence"] = normalise_execution_evidence(exec_evidence)

    # Preserve any top-level keys not explicitly handled into extensions
    handled_keys = {
        "agent_metadata",
        "environment_config",
        "training_config",
        "developer_intent",
        "execution_evidence",
        "extensions",
    }
    for key in raw.keys():
        if key not in handled_keys:
            normalised["extensions"][key] = raw[key]

    return normalised