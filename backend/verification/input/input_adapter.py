"""Input adapter for the verification subsystem.

Accepts structured agent / environment / training data, developer intent,
documentation, and execution evidence — and produces a validated,
canonical ``VerificationInput`` (or ``VerificationContext``) ready for the
downstream intent interpreter and Meta AI-powered verification agent.

The adapter does NOT implement intent interpretation, Meta AI calls, tool
execution, or storage access.  It merely adapts and validates incoming data,
preserving the distinction between structured configuration and
natural-language intent, and supporting optional / incomplete inputs.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import ValidationError

from backend.verification.models import VerificationInput
from backend.verification.exceptions import InputValidationError
from .schema_normalizer import (
    normalise_verification_input,
)


# ---------------------------------------------------------------------------
# Public adapter function
# ---------------------------------------------------------------------------

def adapt_input(
    raw: Dict[str, Any],
    *,
    create_context: bool = True,
) -> VerificationInput:
    """Adapt and validate raw verification input into a canonical
    ``VerificationInput``.

    Args:
        raw: A dictionary containing some or all of the following keys:
            - ``agent_metadata``          — agent identity / type / template
            - ``environment_config``      — environment configuration dict
            - ``training_config``         — training hyper-parameters dict
            - ``developer_intent``        — natural-language description
            - ``execution_evidence``      — observed metrics / rewards /
              events / logs / traces
            - Any other keys are preserved in ``extensions``.
        create_context: If ``True`` (default), the returned
            ``VerificationInput`` can be wrapped in a
            ``VerificationContext`` by the caller.  If ``False``, only
            ``VerificationInput`` is returned.

    Returns:
        A validated ``VerificationInput`` instance.

    Raises:
        ``InputValidationError``: If the input cannot be normalised or
            fails Pydantic validation (e.g. missing ``agent_metadata``).
        ``TypeError``: If *raw* is not a ``dict``.
    """
    if not isinstance(raw, dict):
        raise InputValidationError(
            "Verification input must be a dictionary, "
            f"got {type(raw).__name__}"
        )

    # 1️⃣ Normalise known fields
    normalised = normalise_verification_input(raw)

    # 2️⃣ Construct the canonical VerificationInput
    #    The model itself enforces that ``agent_metadata`` is present
    #    and that ``extra = "allow```` preserves unknown fields.
    try:
        vi = VerificationInput(**normalised)
    except ValidationError as exc:
        # Re-raise as our domain‑specific exception with safe message
        from backend.verification.exceptions import InputValidationError

        raise InputValidationError(
            f"Failed to construct VerificationInput: {exc.errors()}"
        ) from exc

    # 3️⃣ Optional: wrap in VerificationContext if requested
    #    The context adds runtime identifiers (run_id, env_id, timestamps)
    #    without requiring them — they remain ``Optional``.
    if create_context:
        # Build a minimal context; caller can enrich later

        # ctx = build_context(vi)
        # Return the input; the context is available separately.
        # We attach it as a convenience so callers don't need an extra step.
        # Note: VerificationInput does not have a ``context`` field,
        # so we return just the input and let the caller use the context.
        return vi

    return vi


# ---------------------------------------------------------------------------
# Legacy compatibility: accept keyword arguments for convenience
# ---------------------------------------------------------------------------

def adapt_from_parts(
    *,
    agent_metadata: Optional[Dict[str, Any]] = None,
    environment_config: Optional[Dict[str, Any]] = None,
    training_config: Optional[Dict[str, Any]] = None,
    developer_intent: Optional[str] = None,
    execution_evidence: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> VerificationInput:
    """Adapt verification input from explicit parts.

    This is a convenience wrapper that builds the raw dictionary from
    separate components and delegates to ``adapt_input``.  It is useful
    when callers have the components already separated rather than as a
    single merged dict.

    All arguments are optional — the resulting ``VerificationInput`` will
    contain only the provided fields.  Missing ``agent_metadata`` will be
    caught by the model validator.

    Example::
        input_ = adapt_from_parts(
            agent_metadata={"agent_type": "ppo"},
            developer_intent="agent should reach the goal",
        )

    Raises:
        ``InputValidationError``: If ``agent_metadata`` is missing or
            invalid, or if any component fails normalisation.
    """
    # Build the raw dict only from provided, non-None parts
    parts: Dict[str, Any] = {}
    if agent_metadata is not None:
        parts["agent_metadata"] = agent_metadata
    if environment_config is not None:
        parts["environment_config"] = environment_config
    if training_config is not None:
        parts["training_config"] = training_config
    if developer_intent is not None:
        parts["developer_intent"] = developer_intent
    if execution_evidence is not None:
        parts["execution_evidence"] = execution_evidence
    # Pass through any extra kwargs
    parts.update(kwargs)

    return adapt_input(parts)