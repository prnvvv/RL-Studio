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


def _extract_metric_timestamp(
    source: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Extract a timestamp string from a metric source dict, if present."""
    if source is None:
        return None
    ts = source.get("timestamp")
    if isinstance(ts, str):
        return ts
    if isinstance(ts, (int, float)):
        # Assume it's a Unix timestamp; convert to ISO string approximation
        from datetime import datetime, timezone
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return None


def _compare_with_threshold(
    expected: Optional[float],
    actual: Optional[float],
    operator: str,
    tolerance: Optional[float],
) -> Dict[str, Any]:
    """Compare an actual value against an expected threshold.

    Returns a dict with ``status`` and ``details``.
    """
    if expected is None or actual is None:
        return {"status": "unknown", "details": "missing expected or actual value"}

    diff = actual - expected

    if operator == "==":
        if tolerance is not None:
            if abs(diff) <= tolerance:
                return {"status": "pass", "details": f"|actual - expected|={abs(diff):.2f} <= tolerance={tolerance}"}
            return {"status": "fail", "details": f"|actual - expected|={abs(diff):.2f} > tolerance={tolerance}"}
        if diff == 0:
            return {"status": "pass", "details": {"detail": "exact match"}}
        return {"status": "fail", "details": {"detail": f"expected={expected}, actual={actual}"}}

    elif operator == ">=":
        threshold = -tolerance if tolerance is not None else 0
        if diff >= threshold:
            return {"status": "pass", "details": f"actual - expected >= {threshold}"}
        return {"status": "fail", "details": f"actual - expected < {threshold}"}

    elif operator == "<=":
        threshold = tolerance if tolerance is not None else 0
        if diff <= threshold:
            return {"status": "pass", "details": f"actual - expected <= {threshold}"}
        return {"status": "fail", "details": f"actual - expected > {threshold}"}

    elif operator == ">":
        threshold = tolerance if tolerance is not None else 0
        if diff > threshold:
            return {"status": "pass", "details": f"actual - expected > {threshold}"}
        return {"status": "fail", "details": f"actual - expected <= {threshold}"}

    elif operator == "<":
        threshold = tolerance if tolerance is not None else 0
        if diff < threshold:
            return {"status": "pass", "details": f"actual - expected < {threshold}"}
        return {"status": "fail", "details": f"actual - expected >= {threshold}"}

    elif operator == "!=":
        if diff != 0:
            return {"status": "pass", "details": {"detail": "values differ"}}
        return {"status": "fail", "details": {"detail": "values are equal"}}

    else:
        return {"status": "unknown", "details": {"detail": f"Unsupported operator: {operator!r}"}}


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

    # Determine actual value from available sources
    if metric_observations is not None and len(metric_observations) > 0:
        # Use the first observation's value
        first_obs = metric_observations[0]
        if hasattr(first_obs, "value"):
            actual = float(first_obs.value)
        elif isinstance(first_obs, dict):
            actual = _extract_metric_value(first_obs)
        evidence_parts.append(f"metric_observations:{len(metric_observations)}")
    elif metric_values is not None and len(metric_values) > 0:
        # Use the first value
        actual = float(metric_values[0])
        evidence_parts.append(f"metric_values:{len(metric_values)}")
    elif thresholds is not None:
        # No observations, but thresholds are defined; return UNKNOWN
        from backend.verification.models import VerificationCheckResult

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
        from backend.verification.models import VerificationCheckResult

        return VerificationCheckResult(
            requirement_id=requirement.id,
            status="unknown",
            expected=expected,
            actual=None,
            tolerance=None,
            evidence_refs=evidence_parts,
            details={"note": "No metric value available for comparison"},
        )

    # Determine the comparison operator and tolerance
    if thresholds is not None and expected is not None:
        # Look up the threshold for the relevant metric name
        metric_name = metric_names[0] if metric_names else None
        if metric_name and metric_name in thresholds:
            threshold_config = thresholds[metric_name]
            operator = threshold_config.get("operator", "==")
            tolerance = threshold_config.get("tolerance")
        else:
            # Fall back to requirement's operator/tolerance
            operator = requirement.comparison_operator or "=="
            tolerance = requirement.tolerance
    else:
        operator = requirement.comparison_operator or "=="
        tolerance = requirement.tolerance

    # Perform the comparison
    comparison_result = _compare_with_threshold(expected, actual, operator, tolerance)

    from backend.verification.models import VerificationCheckResult

    result = VerificationCheckResult(
        requirement_id=requirement.id,
        status=comparison_result["status"],
        expected=expected,
        actual=actual,
        tolerance=tolerance,
        evidence_refs=evidence_parts,
        details=comparison_result["details"],
    )

    # Add evidence references for metric observations
    if metric_observations is not None:
        for i, obs in enumerate(metric_observations[:3]):  # first 3
            obs_ref = f"metric_obs:{i}"
            if hasattr(obs, "id"):
                result.evidence_refs.append(obs_ref)
            elif isinstance(obs, dict) and "metric_name" in obs:
                result.evidence_refs.append(obs_ref)

    return result


# ---------------------------------------------------------------------------
# Module initialisation: no side effects beyond function definitions.
# ---------------------------------------------------------------------------

# Ensure the module can be imported without side effects beyond function
# definitions and the harmless helper functions above.  No API calls, no
# network hooks, no registry mutations occur at module load time.