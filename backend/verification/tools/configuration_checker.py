"""Environment and configuration verification checker.

Verifies developer requirements against the configuration that is actually
available from the existing system.  Only implements checks supported by real
configuration data and existing contracts.

See ``backend/verification/tools/`` for the package README and integration notes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.verification.models import (
    VerificationCheckResult,
    VerificationRequirement,
    CheckStatus,
    RequirementType,
    EvidenceReference,
)
from backend.verification.exceptions import InputValidationError, EvidenceUnavailableError


def _extract_config_value(
    config: Dict[str, Any],
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
    details: Dict[str, Any],
    source: str,
    run_identifier: Optional[str] = None,
    environment_identifier: Optional[str] = None,
) -> Dict[str, Any]:
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


def execute_check(
    check_id: str,
    requirement: VerificationRequirement,
    config: Optional[Dict[str, Any]],
    *,
    source: str = "configuration",
) -> VerificationCheckResult:
    """Execute a configuration verification check.

    Compares the requirement's expected value against the actual configured
    value.  Only supports checks where the expected value and a retrievable
    configured value are both available.

    Args:
        check_id: Identifier for this check (used for evidence provenance).
        requirement: The ``VerificationRequirement`` describing what is expected.
        config: The actual configuration dict from the environment/system.
        source: Human-readable source label for evidence provenance.

    Returns:
        A ``VerificationCheckResult`` with status ``PASS``, ``FAIL``,
        ``UNKNOWN``, or ``BLOCKED``.
    """
    # Support only reward-type requirements; other types return UNKNOWN.
    if requirement.type.value != RequirementType.reward.value:
        from backend.verification.models import VerificationCheckResult

        return VerificationCheckResult(
            requirement_id=requirement.id,
            status=CheckStatus.UNKNOWN,
            expected=requirement.expected_value,
            actual=None,
            tolerance=None,
            evidence_refs=[],
            details={"error": f"Unsupported requirement type: {requirement.type}"},
        )

    # Retrieve the configured reward value.
    configured_value = _extract_config_value(config, "reward") if config else None

    expected = requirement.expected_value
    actual = configured_value

    # If either side is missing, return UNKNOWN (not FAIL).
    if expected is None or actual is None:
        from backend.verification.models import VerificationCheckResult

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

    # Perform comparison
    comparison_result = _compare_numeric(expected, actual, operator, tolerance)

    from backend.verification.models import VerificationCheckResult

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
    tolerance: Optional[float],
) -> Dict[str, Any]:
    """Compare two numeric values using the given operator and tolerance.

    Returns a dict with ``status`` and a plain‑string ``description``.
    """
    diff = actual - expected

    if operator == "==":
        if tolerance is not None:
            if abs(diff) <= tolerance:
                return {"status": "pass", "description": f"|actual - expected|={abs(diff):.2f} <= tolerance={tolerance}"}
            return {"status": "fail", "description": f"|actual - expected|={abs(diff):.2f} > tolerance={tolerance}"}
        # No tolerance: exact match
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


# ---------------------------------------------------------------------------
# Module initialisation: no side effects beyond function definitions.
# ---------------------------------------------------------------------------

# Ensure the module can be imported without side effects beyond function
# definitions and the harmless helper functions above.  No API calls, no
# network hooks, no registry mutations occur at module load time.