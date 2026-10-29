"""Consistent exception hierarchy for the verification subsystem.

All exceptions inherit from ``VerificationError`` and carry a stable machine-
readable error code, a safe human-readable message, and optional structured
details with correlation/verification IDs.  Secrets, credentials, raw prompts,
or enormous logs must NOT appear in public-facing message fields.

Error codes follow the pattern ``VERB-XXX`` where ``VERB`` describes the
failure category and ``XXX`` is a three-digit ordinal.
"""

from __future__ import annotations

from typing import Any


class VerificationError(Exception):
    """Base exception for all verification-subsystem errors.

    Subclasses must set ``error_code`` (str) and may provide ``details`` (Dict[
    str, Any]) and ``correlation_id`` (Optional[str]).
    """

    error_code: str = "VERG-000"
    """Stable machine-readable error code."""

    def __init__(
        self,
        message: str = "An unexpected verification error occurred",
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.correlation_id = correlation_id or self._generate_id()

    def _generate_id(self) -> str:
        import uuid

        return str(uuid.uuid4())[:8]

    def __str__(self) -> str:
        base = self.message
        if self.details:
            base += f" [code={self.error_code}]"
        if self.correlation_id:
            base += f" [correlation_id={self.correlation_id}]"
        return base


# ---------------------------------------------------------------------------
# 1. Input validation / normalisation failure
# ---------------------------------------------------------------------------


class InputValidationError(VerificationError):
    """Raised when verification input or context fails validation rules.

    Example: missing required fields, invalid UUIDs, malformed timestamps,
    inconsistent configuration shapes.
    """

    error_code: str = "VERG-001"


# ---------------------------------------------------------------------------
# 2. Intent interpretation failure
# ---------------------------------------------------------------------------


class IntentInterpretationError(VerificationError):
    """Raised when the intent interpreter cannot produce structured
    requirements from the given input.

    Example: natural-language intent is too ambiguous, required fields are
    absent, or the input contains contradictions that cannot be resolved.
    """

    error_code: str = "VERG-002"


# ---------------------------------------------------------------------------
# 3. Planning failure
# ---------------------------------------------------------------------------


class PlanningError(VerificationError):
    """Raised by the workflow planner when a valid plan cannot be generated.

    Example: circular dependencies among check steps, unresolvable requirement
    types, or missing evidence that cannot be inferred.
    """

    error_code: str = "VERG-003"


# ---------------------------------------------------------------------------
# 4. Unsupported verification capability
# ---------------------------------------------------------------------------


class UnsupportedCapabilityError(VerificationError):
    """Raised when a requested verification operation is not supported by the
    current architecture configuration.

    Example: attempting to run an ML/DL anomaly check when no model is loaded,
    or requesting a check type that has not been registered.
    """

    error_code: str = "VERG-004"


# ---------------------------------------------------------------------------
# 6. Guardrail violation
# ---------------------------------------------------------------------------

class GuardrailViolation(VerificationError):
    """Raised when a deterministic verification check violates a guardrail
    or constraint, blocking a PASS status.

    Example: reward below threshold, forbidden event recorded, metric order
    independent failure, NaN/inf metric values.
    """
    error_code: str = "VERG-009"


class EvidenceUnavailableError(VerificationError):
    """Raised when required evidence cannot be located or accessed.

    Example: a ``VerificationTool`` requests evidence that does not exist,
    an ``EvidenceProvider`` cannot access the configured store, or an
    ``EvidenceReference`` points to a missing artifact.
    """

    error_code: str = "VERG-005"


# ---------------------------------------------------------------------------
# 6. Verification execution failure
# ---------------------------------------------------------------------------


class VerificationExecutionError(VerificationError):
    """Raised when a verification check or workflow step fails to execute
    correctly.

    This is distinct from ``VerificationError.FAIL`` — an operational error
    during a check does not mean the requirement was violated; it means the
    check itself broke.
    """

    error_code: str = "VERG-006"


# ---------------------------------------------------------------------------
# 7. Meta AI provider failure
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 8. LLM guardrail violation
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# End of module
# ---------------------------------------------------------------------------


class MetaAIProviderError(VerificationError):
    """Raised when the Meta AI provider cannot be reached, refuses the
    request, times out, or returns malformed output.

    Sub‑classes may add detail, but the base class preserves a safe message
    that does not leak credentials or system prompts.
    """

    error_code: str = "VERG-007"


# ---------------------------------------------------------------------------
# 8. Persistence failure
# ---------------------------------------------------------------------------


class PersistenceError(VerificationError):
    """Raised when verification data cannot be persisted or retrieved from
    the selected storage backend.

    Example: database connection failure, corrupted persisted record, or
    incompatible schema version when reloading a previous result.
    """

    error_code: str = "VERG-008"


# ---------------------------------------------------------------------------
# Helpful mixin: add error_code / correlation_id to any exception
# ---------------------------------------------------------------------------

class _VerificationErrorMixin:
    """Mixin that ensures any Exception subclass gets ``error_code`` and
    ``correlation_id`` attributes without altering its inheritance chain.

    Use sparingly; prefer the explicit exception classes defined above.
    """

    def __init__(
        self,
        *args: object,
        error_code: str = "VERG-999",
        correlation_id: str | None = None,
        **kwargs: object,
    ):
        super().__init__(*args, **kwargs)
        self.error_code = error_code
        self.correlation_id = correlation_id or self._generate_id()

    def _generate_id(self) -> str:
        import uuid

        return str(uuid.uuid4())[:8]


# ---------------------------------------------------------------------------
# Convenience: raise ... from exc for chain preservation
# ---------------------------------------------------------------------------

def chain_error(
    exc: Exception,
    message: str,
    error_code: str = "VERG-999",
) -> None:
    """Re-raise *exc* with a new message while preserving the original trace.

    Typical usage::

        try:
            ...
        except SomeError:
            raise chain_error(SomeError(), "wrap message", error_code="VERG-001") from None

    The ``from None`` suppresses the original trace if desired; omit it to
    keep the full chain.
    """
    exc.message = message
    exc.error_code = error_code
    raise exc


# ---------------------------------------------------------------------------
# End of module
# ---------------------------------------------------------------------------

# Ensure the module can be imported without side effects beyond class
# definition.  No runtime side effects, no import hooks, no registry
# mutations occur at module load time.