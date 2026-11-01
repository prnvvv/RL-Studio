"""Deterministic statistical anomaly detection over metric observations.

An anomaly is a **signal**, not a fault (AGENTS.md §6).  This detector never
changes a verification status and never claims a contract violation.  It only
reports observations that are far from the metric's own recent central
tendency so that a developer (or the advisory investigator) can look closer.

The score is a bounded heuristic based on the standard score (z-score).  It is
deliberately *not* described as a calibrated probability.
"""

from __future__ import annotations

import math

from backend.verification.models import (
    AnomalyObservation,
    AnomalyType,
    MetricObservation,
    VerificationContext,
)

#: Default standard-score magnitude at which an observation is flagged.
DEFAULT_Z_THRESHOLD = 3.0

#: Minimum number of usable numeric observations before detecting anything.
MIN_OBSERVATIONS = 3


def _numeric(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _evidence_ref(observation: MetricObservation, index: int) -> str:
    extra = observation.model_extra or {}
    for key in ("observation_id", "metric_id", "id"):
        candidate = extra.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    # Positional provenance within the supplied observation list: stable and
    # traceable back to the caller's own input, never an invented identifier.
    return f"metric[{index}]"


def _score(distance: float, threshold: float) -> float:
    """Map a standard-score distance into ``[0, 1)``.

    ``0.5`` is reached exactly at the threshold; the value is monotonic and
    bounded, which is all the schema requires.
    """
    return round(distance / (distance + threshold), 6)


def detect_anomalies(
    observations: list[MetricObservation],
    context: VerificationContext | None = None,
    *,
    threshold: float = DEFAULT_Z_THRESHOLD,
) -> list[AnomalyObservation]:
    """Return anomaly observations derived from *observations*.

    Observations are grouped by ``metric_name``.  A group needs at least
    :data:`MIN_OBSERVATIONS` finite values and a non-zero standard deviation
    before anything can be flagged.
    """
    if threshold <= 0:
        raise ValueError("threshold must be positive")

    grouped: dict[str, list[tuple[int, float]]] = {}
    for index, observation in enumerate(observations or []):
        value = _numeric(observation.value)
        if value is None:
            continue
        grouped.setdefault(observation.metric_name, []).append((index, value))

    anomalies: list[AnomalyObservation] = []
    for metric_name, entries in sorted(grouped.items()):
        values = [value for _, value in entries]
        if len(values) < MIN_OBSERVATIONS:
            continue
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        if variance <= 0:
            continue
        stdev = math.sqrt(variance)
        for index, value in entries:
            distance = abs(value - mean) / stdev
            if distance < threshold:
                continue
            anomalies.append(
                AnomalyObservation(
                    anomaly_type=AnomalyType.statistical,
                    score=_score(distance, threshold),
                    threshold=threshold,
                    evidence_refs=[_evidence_ref(observations[index], index)],
                    description=(
                        f"{metric_name}={value:g} is {distance:.2f} standard "
                        f"deviations from the mean {mean:g} "
                        f"(n={len(values)})"
                    ),
                )
            )
    return anomalies


class StatisticalAnomalyDetector:
    """Object form implementing the ``AnomalyDetector`` protocol."""

    def __init__(self, threshold: float = DEFAULT_Z_THRESHOLD) -> None:
        self.threshold = threshold

    def detect(
        self,
        observations: list[MetricObservation],
        context: VerificationContext | None = None,
    ) -> list[AnomalyObservation]:
        return detect_anomalies(observations, context, threshold=self.threshold)


__all__ = [
    "DEFAULT_Z_THRESHOLD",
    "MIN_OBSERVATIONS",
    "StatisticalAnomalyDetector",
    "detect_anomalies",
]
