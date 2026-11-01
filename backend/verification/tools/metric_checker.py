"""Metric and threshold verification checker.

Compares metric observations that were **actually recorded** with an explicit
expected value from a requirement.

Non-negotiable rules (AGENTS.md §4.4):

* A missing expectation is ``UNKNOWN`` — the observed value is never used as
  its own expectation and ``None`` is never silently coerced to ``0.0``.
* Non-finite or missing observations are reported as ``UNKNOWN`` inputs, not
  as violations.
* A ``PASS`` requires at least one real, finite observation.
"""

from __future__ import annotations

import math
from typing import Any

from backend.verification.models import (
    CheckStatus,
    MetricObservation,
    VerificationCheckResult,
    VerificationRequirement,
)


def _classify_observation_value(value: float | None) -> str:
    """Classify a numeric metric value for reporting purposes."""
    if value is None:
        return "missing"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if value == float("inf"):
            return "positive_inf"
        if value == float("-inf"):
            return "negative_inf"
    return "numeric"


def _coerce_value(raw: Any) -> float | None:
    """Coerce a raw observation value into a float, or ``None``."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _extract_from_dict(source: dict[str, Any]) -> tuple[float | None, str | None]:
    """Extract ``(value, metric_name)`` from a dict-like observation."""
    value = _coerce_value(source.get("value"))
    name = source.get("metric_name")
    return value, name if isinstance(name, str) else None


def _evaluate_observation_against_threshold(
    expected: float,
    actual: float,
    operator: str,
    tolerance: float | None,
) -> str:
    """Evaluate one observation against a threshold.

    Returns ``"pass"``, ``"fail"`` or ``"unknown"``.
    """
    diff = actual - expected

    if operator == "==":
        if tolerance is not None:
            return "pass" if abs(diff) <= tolerance else "fail"
        return "pass" if diff == 0 else "fail"

    if operator == ">=":
        threshold = -tolerance if tolerance is not None else 0
        return "pass" if diff >= threshold else "fail"

    if operator == "<=":
        threshold = tolerance if tolerance is not None else 0
        return "pass" if diff <= threshold else "fail"

    if operator == ">":
        threshold = tolerance if tolerance is not None else 0
        return "pass" if diff > threshold else "fail"

    if operator == "<":
        threshold = tolerance if tolerance is not None else 0
        return "pass" if diff < threshold else "fail"

    if operator == "!=":
        return "pass" if diff != 0 else "fail"

    return "unknown"


def _determine_overall_status(
    observation_results: list[str],
) -> CheckStatus:
    """Aggregate per-observation outcomes.

    A single observed failure is a violation; otherwise at least one real pass
    is required for ``PASS``.  Anything else stays ``UNKNOWN``.
    """
    if any(result == "fail" for result in observation_results):
        return CheckStatus.FAIL
    if observation_results and all(result == "pass" for result in observation_results):
        return CheckStatus.PASS
    return CheckStatus.UNKNOWN


def _describe_values(values: list[float]) -> str:
    parts = [
        f"obs[{index}]({_classify_observation_value(value)}:{value})"
        for index, value in enumerate(values)
    ]
    return "; ".join(parts)


def execute_check(
    check_id: str,
    requirement: VerificationRequirement,
    *,
    metric_observations: list[MetricObservation | dict[str, Any]] | None = None,
    metric_values: list[float] | None = None,
    metric_names: list[str] | None = None,
    thresholds: dict[str, dict[str, Any]] | None = None,
    evidence_refs: list[str] | None = None,
    source: str = "metric_check",
) -> VerificationCheckResult:
    """Execute a metric and threshold verification check.

    Args:
        check_id: Identifier for this check (provenance only).
        requirement: The ``VerificationRequirement`` describing the contract.
        metric_observations: Recorded ``MetricObservation`` objects or
            equivalent dicts.
        metric_values: Raw recorded numeric metric values.
        metric_names: Metric names corresponding to *metric_values*.
        thresholds: Optional per-metric ``{operator, tolerance}`` overrides.
        evidence_refs: Real evidence identifiers backing the observations.
        source: Provenance label recorded in ``details``.

    Returns:
        A ``VerificationCheckResult`` with status ``PASS``, ``FAIL`` or
        ``UNKNOWN``.
    """
    expected = requirement.expected_value
    refs: list[str] = list(dict.fromkeys(evidence_refs or []))

    # ------------------------------------------------------------------
    # Phase 1: extract the recorded observations.
    # ------------------------------------------------------------------
    values: list[float] = []
    classifications: list[str] = []
    names_seen: list[str] = []

    if metric_observations:
        for observation in metric_observations:
            name: str | None = None
            if isinstance(observation, MetricObservation):
                value = _coerce_value(observation.value)
                name = observation.metric_name
            elif isinstance(observation, dict):
                value, name = _extract_from_dict(observation)
            else:
                value = _coerce_value(getattr(observation, "value", None))
                name = getattr(observation, "metric_name", None)
            if name is not None:
                names_seen.append(name)
            if value is None:
                values.append(float("nan"))
                classifications.append("missing")
            else:
                values.append(value)
                classifications.append(_classify_observation_value(value))

    elif metric_values:
        for raw in metric_values:
            value = _coerce_value(raw)
            if value is None:
                values.append(float("nan"))
                classifications.append("missing")
            else:
                values.append(value)
                classifications.append(_classify_observation_value(value))

    if not values:
        note = (
            "Thresholds are defined but no metric observation was recorded"
            if thresholds
            else "No metric observation is available for comparison"
        )
        return VerificationCheckResult(
            requirement_id=requirement.id,
            status=CheckStatus.UNKNOWN,
            expected=expected,
            actual=None,
            tolerance=None,
            evidence_refs=refs,
            details={"note": note, "source": source},
            is_mandatory=requirement.is_mandatory,
        )

    # ------------------------------------------------------------------
    # Phase 2: resolve operator and tolerance.
    # ------------------------------------------------------------------
    operator: str = requirement.comparison_operator or "=="
    tolerance = requirement.tolerance

    metric_name = next((name for name in names_seen if thresholds and name in thresholds), None)
    if metric_name is None and thresholds and metric_names:
        metric_name = next((name for name in metric_names if name in thresholds), None)
    if metric_name is not None and thresholds is not None:
        threshold_config = thresholds[metric_name]
        operator = str(threshold_config.get("operator", operator))
        tolerance = threshold_config.get("tolerance", tolerance)

    # ------------------------------------------------------------------
    # Phase 3: expectation gate.
    # ------------------------------------------------------------------
    expected_number = _coerce_value(expected)
    if expected_number is None or not math.isfinite(expected_number):
        return VerificationCheckResult(
            requirement_id=requirement.id,
            status=CheckStatus.UNKNOWN,
            expected=expected,
            actual=values[0] if values else None,
            tolerance=tolerance,
            evidence_refs=refs,
            details={
                "note": (
                    "No finite expected metric value is defined in the "
                    "requirement; recorded observations cannot be evaluated"
                ),
                "source": source,
                "observed_values": _describe_values(values),
            },
            is_mandatory=requirement.is_mandatory,
        )

    # ------------------------------------------------------------------
    # Phase 4: evaluate every observation.
    # ------------------------------------------------------------------
    observation_results: list[str] = []
    failing_indices: list[int] = []
    unknown_indices: list[int] = []

    for index, (value, classification) in enumerate(zip(values, classifications)):
        if not math.isfinite(value):
            observation_results.append("unknown")
            unknown_indices.append(index)
            continue
        outcome = _evaluate_observation_against_threshold(
            expected=expected_number,
            actual=value,
            operator=operator,
            tolerance=tolerance,
        )
        observation_results.append(outcome)
        if outcome == "fail":
            failing_indices.append(index)
        elif outcome == "unknown":
            unknown_indices.append(index)

    status = _determine_overall_status(observation_results)

    note_parts = [
        (
            f"{len(values)} observation(s) evaluated with {operator!r} "
            f"expected={expected_number}"
        )
    ]
    if failing_indices:
        note_parts.append(f"failed indices={failing_indices}")
    if unknown_indices:
        note_parts.append(f"inconclusive indices={unknown_indices}")
    note_parts.append(f"observed={_describe_values(values)}")

    return VerificationCheckResult(
        requirement_id=requirement.id,
        status=status,
        expected=expected,
        actual=values[0],
        tolerance=tolerance,
        evidence_refs=refs,
        details={
            "note": "; ".join(note_parts),
            "source": source,
            "operator": operator,
            "failing_indices": failing_indices,
            "unknown_indices": unknown_indices,
        },
        is_mandatory=requirement.is_mandatory,
    )


__all__ = ["execute_check"]
