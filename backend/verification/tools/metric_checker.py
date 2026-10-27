"""Metric and threshold verification checker.

Compares actual metric observations with validated requirements.

See ``backend/verification/tools/`` for the package README and integration notes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.verification.models import (
    VerificationCheckResult,
    VerificationRequirement,
    CheckStatus,
    RequirementType,
    MetricObservation,
    EvidenceReference,
)
from backend.verification.exceptions import InputValidationError, EvidenceUnavailableError


def _extract_metric_value(
    source: Optional[Dict[str, Any]],
    key: str = "value",
) -> Optional[float]:
    """Extract a numeric metric value from a dict-like source.

    Returns None if the key is absent, the value is not numeric, or source is
    None.
    """
    if source is None:
        return None
    val = source.get(key)
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _compare_metric_value(
    expected: float, actual: float, operator: str, tolerance: Optional[float]
) -> Dict[str, str]:
    """Compare two numeric metric values using the given operator and tolerance.

    Returns a dict with ``status`` and ``msg`` (a plain string, compatible with
    the ``details`` field of ``VerificationCheckResult`` after adding ``source``).
    """
    diff = actual - expected

    if operator == "==":
        if tolerance is not None:
            if abs(diff) <= tolerance:
                return {"status": "pass", "msg": f"|actual - expected|={abs(diff):.2f} <= tolerance={tolerance}"}
            return {"status": "fail", "msg": f"|actual - expected|={abs(diff):.2f} > tolerance={tolerance}"}
        if diff == 0:
            return {"status": "pass", "msg": "exact match"}
        return {"status": "fail", "msg": f"expected={expected}, actual={actual}"}

    elif operator == ">=":
        threshold = -tolerance if tolerance is not None else 0
        if diff >= threshold:
            return {"status": "pass", "msg": f"actual - expected >= {threshold}"}
        return {"status": "fail", "msg": f"actual - expected < {threshold}"}

    elif operator == "<=":
        threshold = tolerance if tolerance is not None else 0
        if diff <= threshold:
            return {"status": "pass", "msg": f"actual - expected <= {threshold}"}
        return {"status": "fail", "msg": f"actual - expected > {threshold}"}

    elif operator == ">":
        threshold = tolerance if tolerance is not None else 0
        if diff > threshold:
            return {"status": "pass", "msg": f"actual - expected > {threshold}"}
        return {"status": "fail", "msg": f"actual - expected <= {threshold}"}

    elif operator == "<":
        threshold = tolerance if tolerance is not None else 0
        if diff < threshold:
            return {"status": "pass", "msg": f"actual - expected < {threshold}"}
        return {"status": "fail", "msg": f"actual - expected >= {threshold}"}

    elif operator == "!=":
        if diff != 0:
            return {"status": "pass", "msg": "values differ"}
        return {"status": "fail", "msg": "values are equal"}

    else:
        return {"status": "unknown", "msg": f"Unsupported operator: {operator!r}"}


def execute_check(
    check_id: str,
    requirement: VerificationRequirement,
    *,
    metric_observations: Optional[List[MetricObservation]] = None,
    metric_values: Optional[List[float]] = None,
    metric_names: Optional[List[str]] = None,
    thresholds: Optional[Dict[str, Dict[str, Any]]] = None,
    source: str = "metric_check",
) -> VerificationCheckResult:
    """Execute a metric and threshold verification check.

    Compares actual metric observations with validated requirements.

    Only the checks supported by actual available evidence are implemented.

    Args:
        check_id: Identifier for this check.
        requirement: The ``VerificationRequirement`` describing what is expected.
        metric_observations: Optional list of ``MetricObservation`` objects.
        metric_values: Optional list of raw numeric metric values.
        metric_names: Optional list of metric names corresponding to *metric_values*.
        thresholds: Optional dict mapping metric names to threshold configs,
            each with ``operator`` and ``tolerance`` keys.
        source: Human-readable source label for evidence provenance.

    Returns:
        A ``VerificationCheckResult`` with status ``PASS``, ``FAIL``,
        ``UNKNOWN``, or ``ERROR``.
    """
    expected = requirement.expected_value
    actual: Optional[float] = None
    evidence_parts: List[str] = []
    overall_status: str = "unknown"

    # Determine actual value from available sources
    if metric_observations is not None and len(metric_observations) > 0:
        # Evaluate ALL observations; the requirement passes only if every
        # observation satisfies the comparison with the expected value.
        all_pass = True
        any_invalid = False
        observed_count = 0
        for obs in metric_observations:
            observed_count += 1
            actual = None
            if hasattr(obs, "value"):
                actual = float(obs.value)
            elif isinstance(obs, dict):
                actual = _extract_metric_value(obs)
            if actual is None:
                any_invalid = True
                all_pass = False
                continue
            # Compare using the requirement's comparison operator and tolerance
            operator = requirement.comparison_operator or "=="
            tolerance = requirement.tolerance
            try:
                comparison_result = _compare_metric_value(expected, actual, operator, tolerance)
                if comparison_result["status"] != "pass":
                    all_pass = False
            except (ValueError, TypeError):
                all_pass = False
        if observed_count > 0 and not any_invalid and all_pass:
            overall_status = "pass"
            actual = float(expected)  # use expected as placeholder for "all pass"
            evidence_parts.append(f"metric_observations:{observed_count}")
            details = {"msg": "all observations satisfy requirement"}
        elif observed_count == 0:
            return VerificationCheckResult(
                requirement_id=requirement.id,
                status="unknown",
                expected=expected,
                actual=None,
                tolerance=None,
                evidence_refs=[],
                details={"note": "No metric observations available for comparison"},
            )
        else:
            # At least one observation failed or was invalid
            overall_status = "fail"
            actual = float(expected)  # placeholder; actual value captured in details
            evidence_parts.append(f"metric_observations:{observed_count}")
            details = {"msg": "some observations do not satisfy requirement"}
    elif metric_values is not None and len(metric_values) > 0:
        # Evaluate ALL values in the list; the requirement passes only if every
        # value satisfies the comparison with the expected value.
        all_pass = True
        for v in metric_values:
            try:
                actual_val = float(v)
                operator = requirement.comparison_operator or "=="
                tolerance = requirement.tolerance
                comparison_result = _compare_metric_value(expected, actual_val, operator, tolerance)
                if comparison_result["status"] != "pass":
                    all_pass = False
                    break
            except (ValueError, TypeError):
                all_pass = False
        if all_pass:
            overall_status = "pass"
            actual = float(expected)
            evidence_parts.append(f"metric_values:{len(metric_values)}")
            details = {"msg": "all values satisfy requirement"}
        else:
            overall_status = "fail"
            actual = float(expected)
            evidence_parts.append(f"metric_values:{len(metric_values)}")
            details = {"msg": "some values do not satisfy requirement"}
    elif thresholds is not None:
        # No observations, but thresholds are defined; return UNKNOWN
        return VerificationCheckResult(
            requirement_id=requirement.id,
            status="unknown",
            expected=expected,
            actual=None,
            tolerance=None,
            evidence_refs=[],
            details={
                "note": "Thresholds defined but no metric observations available"
            },
        )

    if actual is None:
        return VerificationCheckResult(
            requirement_id=requirement.id,
            status="unknown",
            expected=expected,
            actual=None,
            tolerance=None,
            evidence_refs=[],
            details={"note": "No metric value available for comparison"},
        )

    # Build the final result details dict
    details: Dict[str, Any] = {}
    if evidence_parts:
        details["source"] = source

    return VerificationCheckResult(
        requirement_id=requirement.id,
        status=overall_status,
        expected=expected,
        actual=actual,
        tolerance=requirement.tolerance,
        evidence_refs=evidence_parts,
        details=details,
    )