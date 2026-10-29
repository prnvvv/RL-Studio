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


def _classify_observation_value(value: Optional[float]) -> str:
    """Classify a numeric metric value for reporting purposes."""
    if value is None:
        return "missing"
    if isinstance(value, float):
        if value != value:  # NaN check
            return "nan"
        if value == float("inf"):
            return "positive_inf"
        if value == float("-inf"):
            return "negative_inf"
    return "numeric"


def _evaluate_observation_against_threshold(
    expected: float,
    actual: float,
    operator: str,
    tolerance: Optional[float],
) -> str:
    """Evaluate a single observation against a threshold.

    Returns one of: 'pass', 'fail', 'unknown'.
    """
    diff = actual - expected

    if operator == "==":
        if tolerance is not None:
            if abs(diff) <= tolerance:
                return "pass"
            return "fail"
        # No tolerance: exact match
        if diff == 0:
            return "pass"
        return "fail"

    elif operator == ">=":
        threshold = -tolerance if tolerance is not None else 0
        if diff >= threshold:
            return "pass"
        return "fail"

    elif operator == "<=":
        threshold = tolerance if tolerance is not None else 0
        if diff <= threshold:
            return "pass"
        return "fail"

    elif operator == ">":
        threshold = tolerance if tolerance is not None else 0
        if diff > threshold:
            return "pass"
        return "fail"

    elif operator == "<":
        threshold = tolerance if tolerance is not None else 0
        if diff < threshold:
            return "pass"
        return "fail"

    elif operator == "!=":
        if diff != 0:
            return "pass"
        return "fail"

    else:
        return "unknown"


def _determine_overall_status(observation_results: List[str]) -> str:
    """Determine the overall status from per-observation results.

    Rules:
    - If any observation fails -> overall FAIL
    - If all observations pass -> overall PASS
    - If some observations are missing/unknown and none fail -> UNKNOWN
    """
    has_fail = any(r == "fail" for r in observation_results)
    all_pass = all(r == "pass" for r in observation_results)
    has_unknown_or_missing = any(
        r in ("unknown", "missing") for r in observation_results
    )

    if has_fail:
        return "fail"
    elif all_pass:
        return "pass"
    elif has_unknown_or_missing and not all_pass:
        return "unknown"
    else:
        return "unknown"


def _build_details_dict(
    operator: str,
    tolerance: Optional[float],
    observation_count: int,
    failing_indices: List[int],
    all_values: List[float],
    expected: float,
) -> Dict[str, str]:
    """Build a details dict that is always Pydantic-compatible.

    Returns a dict with a ``note`` key whose value is a plain string.
    Never returns nested dicts or arbitrary structures, to avoid
    ``pydantic.ValidationError: Input should be a valid dictionary``.
    """
    obs_descriptions: List[str] = []
    for i, val in enumerate(all_values):
        cls = _classify_observation_value(val)
        obs_descriptions.append(f"obs[{i}]({cls}:{val})")

    if failing_indices:
        fail_parts: List[str] = []
        for i in failing_indices:
            actual = all_values[i]
            diff_val = actual - expected
            fail_parts.append(f"obs[{i}]: {operator} expected={expected} diff={diff_val:.2f}")
        fail_detail = "; ".join(fail_parts)
        note = (
            f"Metric check: {observation_count} observations, "
            f"{operator} expected={expected}; "
            f"failed: {fail_detail}; "
            f"all_values: {'; '.join(obs_descriptions)}"
        )
    else:
        note = (
            f"Metric check: {observation_count} observations, "
            f"{operator} expected={expected}; "
            f"all_values: {'; '.join(obs_descriptions)}"
        )

    return {"note": note}


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
        from datetime import datetime, timezone

        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return None


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

    Key differences from the original implementation:
    - Evaluates ALL metric observations, not just the first one.
    - If any observation fails the comparison, the overall result is FAIL.
    - NaN, positive infinity, negative infinity, and missing values are
      classified and reported explicitly.
    - The ``details`` field is always a dict with a ``note`` string; nested
      dicts are avoided to prevent ``pydantic.ValidationError``.
    - Handles ``metric_observations``, ``metric_values``, and ``thresholds``
      paths consistently.

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
    evidence_parts: List[str] = []

    # ------------------------------------------------------------------
    # Phase 1: Extract actual values from the available source(s).
    # ------------------------------------------------------------------

    all_actuals: List[float] = []
    all_classifications: List[str] = []

    # Path A: metric_observations (list of MetricObservation)
    if metric_observations is not None and len(metric_observations) > 0:
        for obs in metric_observations:
            if hasattr(obs, "value") and obs.value is not None:
                val = float(obs.value)
                all_actuals.append(val)
                all_classifications.append(_classify_observation_value(val))
            elif isinstance(obs, dict):
                val = _extract_metric_value(obs)
                if val is not None:
                    all_actuals.append(val)
                    all_classifications.append(_classify_observation_value(val))
                else:
                    all_actuals.append(float("nan"))
                    all_classifications.append("missing")
            else:
                all_actuals.append(float("nan"))
                all_classifications.append("missing")
        evidence_parts.append(f"metric_observations:{len(metric_observations)}")

    # Path B: metric_values (list of raw floats)
    elif metric_values is not None and len(metric_values) > 0:
        for val in metric_values:
            if val is not None:
                all_actuals.append(float(val))
                all_classifications.append(_classify_observation_value(float(val)))
            else:
                all_actuals.append(float("nan"))
                all_classifications.append("missing")
        evidence_parts.append(f"metric_values:{len(metric_values)}")

    # Path C: thresholds defined but no observations
    elif thresholds is not None:
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

    # Path D: no evidence available at all
    if not all_actuals:
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

    # ------------------------------------------------------------------
    # Phase 2: Determine operator and tolerance.
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Phase 3: Evaluate every observation against the threshold.
    # ------------------------------------------------------------------

    # If no expected value is available, all evaluations are inconclusive.
    if expected is None:
        # Return UNKNOWN with all observations classified as unknown
        from backend.verification.models import VerificationCheckResult

        all_actuals_copy = list(all_actuals)
        # Classify all values as missing/unknown since there's no expected value
        details = {
            "note": f"Metric check: {len(all_actuals)} observations, "
                    f"no expected value available; all evaluations inconclusive"
        }
        return VerificationCheckResult(
            requirement_id=requirement.id,
            status="unknown",
            expected=expected,
            actual=all_actuals_copy[0] if all_actuals_copy else None,
            tolerance=None,
            evidence_refs=evidence_parts,
            details=details,
        )

    observation_results: List[str] = []
    failing_indices: List[int] = []

    for i, (actual, classification) in enumerate(zip(all_actuals, all_classifications)):
        # Skip NaN/missing observations — treat as unknown, not fail
        if classification in ("nan", "missing"):
            observation_results.append("unknown")
            failing_indices.append(i)  # track for reporting
            continue

        result = _evaluate_observation_against_threshold(
            expected=float(expected),
            actual=actual,
            operator=operator,
            tolerance=tolerance,
        )
        observation_results.append(result)
        if result == "fail":
            failing_indices.append(i)

    # ------------------------------------------------------------------
    # Phase 4: Determine overall status.
    # ------------------------------------------------------------------

    overall = _determine_overall_status(observation_results)

    # ------------------------------------------------------------------
    # Phase 5: Build the result.
    # ------------------------------------------------------------------

    details = _build_details_dict(
        operator=operator,
        tolerance=tolerance,
        observation_count=len(all_actuals),
        failing_indices=failing_indices,
        all_values=all_actuals,
        expected=float(expected) if expected is not None else 0.0,
    )

    from backend.verification.models import VerificationCheckResult

    result = VerificationCheckResult(
        requirement_id=requirement.id,
        status=overall,
        expected=expected,
        actual=all_actuals[0] if all_actuals else None,
        tolerance=tolerance,
        evidence_refs=evidence_parts,
        details=details,
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