"""Read-only summarisation of execution evidence.

The analyser answers "what evidence do we actually have?" without interpreting
it.  It never infers a value that was not supplied: missing data is reported as
missing, so downstream components cannot present a summary as if it were a
measurement.

This module is pure: it takes an already-extracted ``EvidenceBundle`` (or a raw
``execution_evidence`` mapping) and returns plain data.
"""

from __future__ import annotations

from typing import Any

from backend.verification.evidence_validator import EvidenceBundle, extract_evidence


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _metric_values(bundle: EvidenceBundle) -> dict[str, list[float]]:
    grouped: dict[str, list[float]] = {}
    for observation in bundle.metrics:
        if isinstance(observation, dict):
            name = observation.get("name") or observation.get("metric_name")
            raw_value = observation.get("value")
        else:
            name = getattr(observation, "metric_name", None)
            raw_value = getattr(observation, "value", None)
        if not isinstance(name, str) or not name:
            continue
        number = _numeric(raw_value)
        if number is None:
            continue
        grouped.setdefault(name, []).append(number)
    return grouped


def summarise_metrics(bundle: EvidenceBundle) -> dict[str, dict[str, float | int]]:
    """Return per-metric count/min/max/last for the supplied observations."""
    summary: dict[str, dict[str, float | int]] = {}
    for name, values in _metric_values(bundle).items():
        summary[name] = {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "last": values[-1],
        }
    return summary


def summarise_events(bundle: EvidenceBundle) -> dict[str, Any]:
    """Return factual counts about event evidence.

    ``events`` of ``None`` means "no event evidence supplied"; an empty list
    means "explicitly an empty, complete event list".  These are distinct and
    stay distinct here.
    """
    if bundle.events is None:
        return {"supplied": False, "count": None, "event_types": {}}

    event_types: dict[str, int] = {}
    for event in bundle.events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type") or event.get("type")
        if isinstance(event_type, str) and event_type:
            event_types[event_type] = event_types.get(event_type, 0) + 1
    return {
        "supplied": True,
        "count": len(bundle.events),
        "event_types": event_types,
    }


def missing_evidence(bundle: EvidenceBundle) -> list[str]:
    """List the evidence kinds that were not supplied, in a stable order."""
    missing: list[str] = []
    if bundle.observed_reward is None:
        missing.append("observed_reward")
    if bundle.episode is None:
        missing.append("episode")
    if bundle.events is None:
        missing.append("events")
    if not bundle.metrics:
        missing.append("metrics")
    if not bundle.config_view():
        missing.append("configuration")
    return missing


def analyse_execution_evidence(
    evidence: EvidenceBundle | dict[str, Any] | None,
    *,
    environment_config: dict[str, Any] | None = None,
    training_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarise available evidence without interpreting it.

    Args:
        evidence: An already-extracted ``EvidenceBundle`` or a raw
            ``execution_evidence`` mapping.
        environment_config: Used only when ``evidence`` is a raw mapping.
        training_config: Used only when ``evidence`` is a raw mapping.

    Returns:
        A JSON-safe mapping with counts, metric ranges, absent evidence kinds
        and the recorded evidence problems.  No expected/observed judgement is
        made here.
    """
    if isinstance(evidence, EvidenceBundle):
        bundle = evidence
    else:
        bundle = extract_evidence(
            evidence,
            environment_config=environment_config,
            training_config=training_config,
        )

    return {
        "run_identifier": bundle.run_identifier,
        "environment_identifier": bundle.environment_identifier,
        "environment_version": bundle.environment_version,
        "has_any_evidence": bundle.has_any_evidence,
        "evidence_complete": bundle.evidence_complete,
        "reward": {
            "configured_reward": bundle.configured_reward,
            "observed_reward": bundle.observed_reward,
            "evidence_refs": list(bundle.reward_evidence_refs),
        },
        "episode_supplied": bundle.episode is not None,
        "events": summarise_events(bundle),
        "metrics": summarise_metrics(bundle),
        "configuration_keys": sorted(bundle.config_view()),
        "missing_evidence": missing_evidence(bundle),
        "problems": list(bundle.problems),
    }


__all__ = [
    "analyse_execution_evidence",
    "missing_evidence",
    "summarise_events",
    "summarise_metrics",
]
