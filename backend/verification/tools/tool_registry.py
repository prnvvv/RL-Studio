"""Central tool registry and dispatch mechanism for verification checks.

Provides a single, controlled mechanism for the LangGraph workflow to discover
and execute approved verification checks.  Checks are registered by identifier
and dispatch execution to the correct handler function.

Do not implement a competing registry or duplicate existing check logic.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

from backend.verification.models import CheckStatus, VerificationCheckResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry: maps stable check identifiers to handler callables.
# ---------------------------------------------------------------------------

#: Mapping of registered check IDs to their handler callables.
_tool_handlers: dict[str, Callable[..., Any]] = {}

#: Mapping of check IDs to human-readable descriptions.
_tool_descriptions: dict[str, str] = {}

#: Mapping of check IDs to their required argument schemas.
#: Used for argument validation before execution.
_tool_schemas: dict[str, Any] = {}

#: Mapping of check IDs to optional per-check execution timeouts (seconds).
_tool_timeout: dict[str, float | None] = {}

#: Maximum total verification tool execution budget in seconds.  None means no
#: budget.
_total_timeout: float | None = None


def register_check(
    check_id: str,
    handler: Callable[..., Any],
    *,
    description: str = "",
    schema: Any = None,
    timeout: float | None = None,
) -> None:
    """Register a verification check handler in the global registry.

    Args:
        check_id: Stable identifier for the check (e.g. ``"check_reward"``).
        handler: Callable that returns a ``VerificationCheckResult``.
        description: Human-readable description of what the check does.
        schema: Optional schema/validator for ``arguments``.
        timeout: Optional execution timeout in seconds.  None means no timeout.

    Raises:
        ValueError: If *check_id* is already registered (duplicate prevention).
    """
    if check_id in _tool_handlers:
        raise ValueError(f"Check already registered: {check_id!r}")
    _tool_handlers[check_id] = handler
    _tool_descriptions[check_id] = description or check_id
    _tool_schemas[check_id] = schema
    _tool_timeout[check_id] = timeout


def list_checks() -> dict[str, dict[str, Any]]:
    """Return metadata for all currently registered checks."""
    return {
        check_id: {
            "description": _tool_descriptions.get(check_id, ""),
            "schema": str(_tool_schemas.get(check_id, "none")),
            "timeout": _tool_timeout.get(check_id),
        }
        for check_id in _tool_handlers
    }


def is_check_registered(check_id: str) -> bool:
    """Return True if *check_id* is currently registered in the global registry."""
    return check_id in _tool_handlers


def get_check_description(check_id: str) -> str:
    """Return the human-readable description for a registered check."""
    return _tool_descriptions.get(check_id, "")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _error_result(check_id: str, message: str, requirement_id: str = "") -> VerificationCheckResult:
    return VerificationCheckResult(
        requirement_id=requirement_id,
        status=CheckStatus.ERROR,
        expected=None,
        actual=None,
        tolerance=None,
        evidence_refs=[],
        details={"error": message, "check_id": check_id},
    )


def _validate_arguments(check_id: str, arguments: dict[str, Any]) -> None:
    """Validate *arguments* against the registered schema, when present."""
    schema = _tool_schemas.get(check_id)
    if schema is None:
        return

    if hasattr(schema, "model_validate"):
        schema.model_validate(arguments)  # type: ignore[attr-defined]
        return

    if isinstance(schema, dict):
        for key in schema.get("required", []):
            if key not in arguments:
                from backend.verification.exceptions import InputValidationError

                raise InputValidationError(f"Missing required argument: {key!r}")


def _build_call(
    handler: Callable[..., Any],
    check_id: str,
    context: Any,
    arguments: dict[str, Any],
) -> tuple[list[Any], dict[str, Any]]:
    """Map *arguments* onto the handler's declared parameters.

    Handlers in this package follow ``(check_id, requirement, ...)`` while other
    compatible handlers follow ``(context, arguments)``.  The mapping is derived
    from the signature, never by mutating the caller's argument dict.
    """
    signature = inspect.signature(handler)
    parameters = signature.parameters

    if "context" in parameters and "check_id" not in parameters:
        # Generic adapter style: (context, arguments).
        return [context, dict(arguments)], {}

    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    consumed: set[str] = set()

    for name, parameter in parameters.items():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            for key, value in arguments.items():
                if key not in consumed and key not in keyword:
                    keyword[key] = value
            continue
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            continue

        if name == "check_id":
            value = check_id
        elif name == "context":
            value = context
        elif name == "arguments":
            value = dict(arguments)
        elif name in arguments:
            value = arguments[name]
            consumed.add(name)
        elif name == "config":
            value = arguments.get("config")
            consumed.add("config")
        elif parameter.default is not inspect.Parameter.empty:
            continue
        else:
            value = None

        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY or parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD:
            positional.append(value)
        else:
            keyword[name] = value

    return positional, keyword


def execute_check(
    check_id: str,
    context: Any,
    arguments: dict[str, Any],
) -> VerificationCheckResult:
    """Execute a registered verification check and return its result.

    Args:
        check_id: The registered check identifier.
        context: ``VerificationContext`` or equivalent dict-like object.
        arguments: Check-specific arguments.  The caller's dict is never
            mutated.

    Returns:
        A ``VerificationCheckResult`` produced by the handler.  Dispatch and
        handler failures are normalised to ``CheckStatus.ERROR``.
    """
    if check_id not in _tool_handlers:
        return _error_result(check_id, f"Unregistered check: {check_id!r}")

    requirement = arguments.get("requirement")
    requirement_id = getattr(requirement, "id", "") or ""

    try:
        _validate_arguments(check_id, arguments)
    except Exception as exc:
        from backend.verification.exceptions import InputValidationError

        if isinstance(exc, InputValidationError):
            raise
        raise InputValidationError(
            f"Argument schema validation failed for check {check_id!r}: {exc}"
        ) from exc

    handler = _tool_handlers[check_id]

    try:
        positional, keyword = _build_call(handler, check_id, context, arguments)
        result = handler(*positional, **keyword)
    except Exception as exc:  # noqa: BLE001 - boundary: normalise to ERROR
        logger.warning("Verification check %r failed: %s", check_id, exc)
        return _error_result(
            check_id,
            f"Check execution error: {type(exc).__name__}: {exc}",
            requirement_id,
        )

    if not isinstance(result, VerificationCheckResult):
        return _error_result(
            check_id,
            f"Handler did not return VerificationCheckResult: {type(result).__name__}",
            requirement_id,
        )

    if not result.requirement_id and requirement_id:
        result = result.model_copy(update={"requirement_id": requirement_id})

    return result


__all__ = [
    "execute_check",
    "get_check_description",
    "is_check_registered",
    "list_checks",
    "register_check",
]
