"""Environment and configuration verification checker.

Verifies developer requirements against the configuration that is actually
available from the existing system.  Supports all canonical requirement types
and handles numeric and non-numeric configuration values without uncaught
exceptions.

See ``backend/verification/tools/`` for the package README and integration notes.
"""

from __future__ import annotations

import math
from typing import Any

from backend.verification.models import (
    CheckStatus,
    RequirementType,
    VerificationCheckResult,
    VerificationRequirement,
)


def _extract_config_value(
    config: dict[str, Any],
    key: str,
    default: Any = None,
) -> Any:
    """Safely extract a scalar value from a configuration dict.

    Returns *default* if the key is absent or the value is not a simple type.
    """
    if config is None:
        return default
    val = config.get(key, default)
    if isinstance(val, (str, int, float, bool)):
        return val
    return default


def _add_evidence_dict(
    details: dict[str, Any],
    source: str,
    run_identifier: str | None = None,
    environment_identifier: str | None = None,
) -> dict[str, Any]:
    """Add evidence provenance to the details dict."""
    if "source" not in details:
        details["source"] = source
    if run_identifier is not None:
        details["run_identifier"] = run_identifier
    if environment_identifier is not None:
        details["environment_identifier"] = environment_identifier
    return details


# ---------------------------------------------------------------------------
# Configuration checker
# ---------------------------------------------------------------------------

_TYPE_EXTRACTORS: dict[RequirementType, callable] = {
    RequirementType.reward: lambda config, key: _extract_config_value(config, "reward", None),
    RequirementType.termination: lambda config, key: _extract_config_value(config, "max_episodes", None),
    RequirementType.metric: lambda config, key: _extract_config_value(config, "metric_threshold", None),
    RequirementType.event: lambda config, key: _extract_config_value(config, "event_config", None),
    RequirementType.configuration: lambda config, key: _extract_config_value(config, "config_value", None),
    RequirementType.observation: lambda config, key: _extract_config_value(config, "observation_range", None),
    RequirementType.action_space: lambda config, key: _extract_config_value(config, "action_space_bounds", None),
    RequirementType.grid_goal: lambda config, key: _extract_config_value(config, "goal_coordinates", None),
    RequirementType.collision: lambda config, key: _extract_config_value(config, "collision_penalty", None),
}


def execute_check(
    check_id: str,
    requirement: VerificationRequirement,
    config: dict[str, Any] | None,
    *,
    source: str = "configuration",
) -> VerificationCheckResult:
    """Execute a configuration verification check.

    Compares the requirement's expected value against the actual configured
    value.  Supports all canonical requirement types; returns ``UNKNOWN``
    when the configured value for the requirement's type is not available.

    Args:
        check_id: Identifier for this check (used for evidence provenance).
        requirement: The ``VerificationRequirement`` describing what is expected.
        config: The actual configuration dict from the environment/system.
        source: Human-readable source label for evidence provenance.

    Returns:
        A ``VerificationCheckResult`` with status ``PASS``, ``FAIL``,
        ``UNKNOWN``, or ``BLOCKED``.
    """
    # Extract the configured value for this requirement's type.
    extractor = _TYPE_EXTRACTORS.get(requirement.type)
    if extractor is None:
        return VerificationCheckResult(
            requirement_id=requirement.id,
            status=CheckStatus.UNKNOWN,
            expected=requirement.expected_value,
            actual=None,
            tolerance=None,
            evidence_refs=[],
            details={"error": f"Unsupported requirement type: {requirement.type}"},
        )

    configured_value = extractor(config, requirement.type) if config else None

    expected = requirement.expected_value
    actual = configured_value

    # If either side is missing, return UNKNOWN (not FAIL).
    if expected is None or actual is None:
        details = {"note": "Missing configuration or expected value; cannot compare"}
        _add_evidence_dict(details, source)
        return VerificationCheckResult(
            requirement_id=requirement.id,
            status="unknown",
            expected=expected,
            actual=actual,
            tolerance=None,
            evidence_refs=[],
            details=details,
        )

    # Compare using the requirement's comparison operator and tolerance
    operator = requirement.comparison_operator or "=="
    tolerance = requirement.tolerance

    # Perform comparison _compare_numeric now handles non-finite values safely
    try:
        comparison_result = _compare_numeric(expected, actual, operator, tolerance)
    except (ValueError, TypeError) as exc:
        return VerificationCheckResult(
            requirement_id=requirement.id,
            status="error",
            expected=expected,
            actual=actual,
            tolerance=tolerance,
            evidence_refs=[],
            details={"msg": f"Comparison error: {exc}"},
        )

    details = {"description": comparison_result["description"]}
    _add_evidence_dict(details, source)

    return VerificationCheckResult(
        requirement_id=requirement.id,
        status=comparison_result["status"],
        expected=expected,
        actual=actual,
        tolerance=tolerance,
        evidence_refs=[],
        details=details,
    )


def _compare_numeric(
    expected: float,
    actual: float,
    operator: str,
    tolerance: float | None,
) -> dict[str, Any]:
    """Compare two numeric values using the given operator and tolerance.

    Returns a dict with ``status`` and a plain‑string ``description``.
    Handles NaN, positive/negative infinity, and malformed values gracefully.

    Returns:
        A dict with keys ``status`` one of ``'pass'``, ``'fail'``, ``'unknown'``
        and ``description`` a plain string.
    """
    # Handle non-finite values
    if not isinstance(expected, (int, float)) or not isinstance(actual, (int, float)):
        return {"status": "unknown", "description": f"Non-numeric comparison: expected={expected!r}, actual={actual!r}"}

    if math.isnan(expected):  # NaN check
        return {"status": "unknown", "description": "Expected value is NaN; cannot compare"}
    if math.isnan(actual):  # NaN check
        return {"status": "unknown", "description": "Actual value is NaN; cannot compare"}
    if expected == float("inf") or expected == float("-inf"):
        return {"status": "unknown", "description": "Expected value is infinity; cannot compare"}
    if actual == float("inf") or actual == float("-inf"):
        return {"status": "unknown", "description": "Actual value is infinity; cannot compare"}

    diff = actual - expected

    if operator == "==":
        if tolerance is not None:
            if abs(diff) <= tolerance:
                return {"status": "pass", "description": f"|actual - expected|={abs(diff):.2f} <= tolerance={tolerance}"}
            return {"status": "fail", "description": f"|actual - expected|={abs(diff):.2f} > tolerance={tolerance}"}
        if diff == 0:
            return {"status": "pass", "description": "exact match"}
        return {"status": "fail", "description": f"expected={expected}, actual={actual}"}

    elif operator == ">=":
        threshold = -tolerance if tolerance is not None else 0
        if diff >= threshold:
            return {"status": "pass", "description": f"actual - expected >= {threshold}"}
        return {"status": "fail", "description": f"actual - expected < {threshold}"}

    elif operator == "<=":
        threshold = tolerance if tolerance is not None else 0
        if diff <= threshold:
            return {"status": "pass", "description": f"actual - expected <= {threshold}"}
        return {"status": "fail", "description": f"actual - expected > {threshold}"}

    elif operator == ">":
        threshold = tolerance if tolerance is not None else 0
        if diff > threshold:
            return {"status": "pass", "description": f"actual - expected > {threshold}"}
        return {"status": "fail", "description": f"actual - expected <= {threshold}"}

    elif operator == "<":
        threshold = tolerance if tolerance is not None else 0
        if diff < threshold:
            return {"status": "pass", "description": f"actual - expected < {threshold}"}
        return {"status": "fail", "description": f"actual - expected >= {threshold}"}

    elif operator == "!=":
        if diff != 0:
            return {"status": "pass", "description": "values differ"}
        return {"status": "fail", "description": "values are equal"}

    else:
        return {"status": "unknown", "description": f"Unsupported operator: {operator!r}"}