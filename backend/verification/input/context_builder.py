"""Context builder for the verification subsystem.

Assembles normalised inputs into the existing ``VerificationContext`` (or
equivalent canonical context model).  The context preserves — where available
— agent metadata, configurations, developer intent, documentation references,
run/environment identifiers, and execution evidence references, without
performing intent parsing, workflow planning, verification, anomaly detection,
or diagnosis.

Developer-stated information is kept distinguishable from metadata and
observations.  Assumptions are not converted into requirements.  Missing
execution evidence does not imply that training occurred.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.verification.models import VerificationContext, VerificationInput
from backend.verification.exceptions import InputValidationError


# ---------------------------------------------------------------------------
# Core context-building function
# ---------------------------------------------------------------------------

def build_context(
    input_data: VerificationInput,
    *,
    run_identifier: Optional[str] = None,
    environment_identifier: Optional[str] = None,
    environment_version: Optional[str] = None,
) -> VerificationContext:
    """Build a ``VerificationContext`` from a ``VerificationInput``.

    The returned context preserves all information that was present in the
    original input, distinguishes developer-stated intent from structured
    configuration, and marks missing fields as ``None`` rather than inferring
    values.

    Args:
        input_data: A ``VerificationInput`` instance produced by the input
            adapter or normaliser.
        run_identifier: Optional run / experiment ID (e.g. ``run_42``,
            ``experiment_01``).
        environment_identifier: Optional environment ID / name
            (e.g. ``warehouse_v1``, ``sim_01``).
        environment_version: Optional environment version string
            (e.g. ``v1``, ``v2``).

    Returns:
        A ``VerificationContext`` instance with all available information
        from the input, combined with the provided runtime identifiers.

    Raises:
        ``InputValidationError``: If *input_data* is not a valid
            ``VerificationInput`` (should not happen if the adapter was used).
    """
    if not isinstance(input_data, VerificationInput):
        raise InputValidationError(
            "input_data must be a VerificationInstance, "
            f"got {type(input_data).__name__}"
        )

    # Build the context using the canonical model.
    # All fields are Optional — none are required.
    ctx = VerificationContext(
        run_identifier=run_identifier,
        environment_identifier=environment_identifier,
        environment_version=environment_version,
        input=input_data,
        created_at=datetime.now(timezone.utc),
        schema_version=input_data.extensions.get(
            "schema_version", "1.0"
        ),
    )

    return ctx


# ---------------------------------------------------------------------------
# Helper: assemble a VerificationInput from the various source dicts that
# the input layer may receive.  This is used by callers who have not yet
# merged their inputs into a single dictionary.
# ---------------------------------------------------------------------------


def assemble_input(
    *,
    agent_metadata: Optional[Dict[str, Any]] = None,
    environment_config: Optional[Dict[str, Any]] = None,
    training_config: Optional[Dict[str, Any]] = None,
    developer_intent: Optional[str] = None,
    execution_evidence: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> VerificationInput:
    """Assemble a ``VerificationInput`` from separate component dictionaries.

    This is a convenience helper for callers who have not yet merged their
    inputs.  All arguments are optional; missing fields remain absent
    (``None`` / empty) in the resulting input, and the model validator will
    catch any required-field violations (e.g. missing ``agent_metadata``).

    Returns:
        A ``VerificationInput`` instance constructed from the provided
        components.
    """
    from backend.verification.input.input_adapter import adapt_from_parts

    return adapt_from_parts(
        agent_metadata=agent_metadata,
        environment_config=environment_config,
        training_config=training_config,
        developer_intent=developer_intent,
        execution_evidence=execution_evidence,
    )