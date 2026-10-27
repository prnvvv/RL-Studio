"""Central tool registry and dispatch mechanism for verification checks.

Provides a single, controlled mechanism for the LangGraph workflow to discover
and execute approved verification checks.  Checks are registered by identifier
and dispatch execution to the correct handler function.

Do not implement a competing registry or duplicate existing check logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.verification.models import VerificationCheckResult
from backend.verification.exceptions import InputValidationError


# ---------------------------------------------------------------------------
# Registry: maps stable check identifiers to handler callables.
# ---------------------------------------------------------------------------

#: Mapping of registered check IDs to their handler callables.
_tool_handlers: Dict[str, Any] = {}

#: Mapping of check IDs to human-readable descriptions.
_tool_descriptions: Dict[str, str] = {}

#: Mapping of check IDs to their required argument schemas.
#: Used for argument validation before execution.
_tool_schemas: Dict[str, Any] = {}

#: Mapping of check IDs to optional per-check execution timeouts (seconds).
_tool_timeout: Dict[str, Optional[float]] = {}

#: Maximum total verification tool execution budget in seconds.  None means no
#: budget.
_total_timeout: Optional[float] = None


def register_check(
    check_id: str,
    handler: Any,
    *,
    description: str = "",
    schema: Any = None,
    timeout: Optional[float] = None,
) -> None:
    """Register a verification check handler in the global registry.

    After registration, the check can be dispatched by ID from the LangGraph
    controller or any other authorised component.

    Args:
        check_id: Stable identifier for the check (e.g. ``"check_reward_scale"``).
        handler: Callable that accepts ``context`` and ``arguments`` and returns
            a ``VerificationCheckResult``.
        description: Human-readable description of what the check does.
        schema: Optional schema/validator for ``arguments``.  If provided, the
            ``execute_check`` function will validate arguments against it before
            dispatch.
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


def list_checks() -> Dict[str, Dict[str, Any]]:
    """Return metadata for all currently registered checks.

    Returns a dict mapping check IDs to ``{description, schema, timeout}``.
    Useful for introspection and for the LangGraph controller to present to
    the model at planning time.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for check_id in _tool_handlers:
        result[check_id] = {
            "description": _tool_descriptions.get(check_id, ""),
            "schema": str(_tool_schemas.get(check_id, "none")),
            "timeout": _tool_timeout.get(check_id),
        }
    return result


def is_check_registered(check_id: str) -> bool:
    """Return True if *check_id* is currently registered in the global registry."""
    return check_id in _tool_handlers


def get_check_description(check_id: str) -> str:
    """Return the human-readable description for a registered check, or '' if
    unknown."""
    return _tool_descriptions.get(check_id, "")


# ---------------------------------------------------------------------------
# Dispatch: execute a registered check with argument validation and error
# handling.
# ---------------------------------------------------------------------------

def execute_check(
    check_id: str,
    context: Any,
    arguments: Dict[str, Any],
) -> VerificationCheckResult:
    """Execute a registered verification check and return its result.

    The registry validates that *check_id* is known, validates arguments against
    the registered schema (if any), and dispatch to the handler.  All exceptions
    are normalised into ``VerificationCheckResult`` with appropriate status.

    Args:
        check_id: The registered check identifier.
        context: VerificationContext or equivalent dict-like object.
        arguments: Check-specific arguments.  Must conform to the registered
            schema if one was provided at registration time.  Expected keys
            depend on the registered check handler.

    Returns:
        A ``VerificationCheckResult`` produced by the handler.

    Raises:
        ValueError: If *check_id* is not registered.
        InputValidationError: If arguments fail schema validation.
    """
    if check_id not in _tool_handlers:
        return VerificationCheckResult(
            requirement_id="",
            status="error",
            expected=None,
            actual=None,
            tolerance=None,
            evidence_refs=[],
            details={"error": f"Unregistered check: {check_id!r}"},
        )

    handler = _tool_handlers[check_id]
    schema = _tool_schemas.get(check_id)
    timeout = _tool_timeout.get(check_id)

    # Argument schema validation (if provided)
    if schema is not None:
        try:
            # Support both Pydantic BaseModel and dict-based validation
            if hasattr(schema, "model_validate"):
                schema.model_validate(arguments)  # type: ignore[attr-defined]
            elif isinstance(schema, dict):
                # Lightweight dict validation: check required keys exist
                required = schema.get("required", [])
                # Allow missing required keys if the handler can deal with it;
                # the checker will decide what to do with missing data.
                for key in required:
                    if key not in arguments:
                        raise InputValidationError(
                            f"Missing required argument: {key!r}"
                        )
            else:
                # Unknown schema type; skip strict validation but log
                pass
        except InputValidationError:
            raise
        except Exception as exc:
            raise InputValidationError(
                f"Argument schema validation failed for check {check_id!r}: {exc}"
            )

    # Execute the handler — adapt arguments to the handler's expected signature.
    # The handler (checker execute_check) may expect (check_id, requirement, ...)
    # or (context, arguments, ...).  We detect and adapt.
    try:
        # Try the standard adapter: extract requirement from arguments if present
        requirement = arguments.pop("requirement", None)
        # Also try to extract check_id if present
        # Re-invoke handler with adapted arguments
        if requirement is not None and hasattr(handler, "__code__"):
            # For checkers that expect (check_id, requirement, ...)
            import inspect
            sig = inspect.signature(handler)
            param_names = list(sig.parameters.keys())
            if len(param_names) >= 2 and param_names[0] == "check_id" and param_names[1] == "requirement":
                # Handler expects (check_id, requirement, ...); pass check_id from registry
                result = handler(check_id, requirement, **arguments)
            elif len(param_names) >= 1 and param_names[0] == "context":
                # Handler expects (context, arguments, ...)
                args_dict = dict(arguments)
                if requirement is not None:
                    args_dict["requirement"] = requirement
                result = handler(context, args_dict)
            else:
                # Fallback: try original call pattern
                result = handler(context, arguments)
        else:
            # Fallback: try original call pattern
            result = handler(context, arguments)
    except Exception as exc:
        # If adaptation fails, return error result
        return VerificationCheckResult(
            requirement_id="",
            status="error",
            expected=None,
            actual=None,
            tolerance=None,
            evidence_refs=[],
            details={"error": f"Check execution error: {exc}"},
        )

    # Ensure the result is a VerificationCheckResult
    if not isinstance(result, VerificationCheckResult):
        return VerificationCheckResult(
            requirement_id="",
            status="error",
            expected=None,
            actual=None,
            tolerance=None,
            evidence_refs=[],
            details={"error": f"Handler did not return VerificationCheckResult: {type(result).__name__}"},
        )

    # Apply timeout if needed (runtime enforcement is caller + LangGraph
    # responsibility; here we just record that a timeout was configured)
    if timeout is not None:
        pass

    return result


# ---------------------------------------------------------------------------
# Module initialisation: no side effects beyond function definitions.
# ---------------------------------------------------------------------------

# Ensure the module can be imported without side effects beyond function
# definitions and the harmless dict initialisations above.  No API calls,
# no network hooks, no registry mutations occur at module load time.