"""Cross-check consistency of verification plans, results, and evidence.

The consistency checker answers one question: *is this verification payload
internally coherent?*  It does not decide pass/fail (the decision engine does)
and it does not call a model.  Its output is a list of problem strings that
callers surface as warnings or use to block persistence.

Missing evidence is never treated as consistent evidence: callers that know
whether usable evidence was supplied pass ``evidence_available`` so that the
summary reports ``not_evaluable`` instead of a reassuring ``consistent``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from backend.verification.evidence_validator import EvidenceBundle
from backend.verification.models import (
    CheckStatus,
    VerificationCheckResult,
    VerificationRequirement,
)
from backend.verification.result_validator import (
    validate_check_result,
    validate_requirement_alignment,
)

#: Evidence references synthesised by the checkers themselves.  A configuration
#: reference names a location inside caller-supplied configuration, so it is
#: traceable even though it is not an externally supplied record identifier.
_SYNTHETIC_REF_PREFIXES = ("config.",)


def check_result_consistency(
    check_results: dict[str, VerificationCheckResult],
) -> list[str]:
    """Return structural problems across a set of check results."""
    problems: list[str] = []
    for requirement_id, result in check_results.items():
        if result.requirement_id and result.requirement_id != requirement_id:
            problems.append(
                f"{requirement_id}: result belongs to {result.requirement_id}"
            )
        problems.extend(validate_check_result(result))
    return problems


def check_plan_consistency(
    *,
    requirements: list[VerificationRequirement],
    registered_checks: dict[str, str],
    registered_tool_ids: set[str],
) -> list[str]:
    """Return problems with a requirement-to-check dispatch plan."""
    problems: list[str] = []
    planned = set(registered_checks)
    for requirement in requirements:
        if requirement.id not in planned:
            problems.append(f"requirement {requirement.id} is not planned")
    for requirement_id, check_id in registered_checks.items():
        if check_id not in registered_tool_ids:
            problems.append(
                f"requirement {requirement_id} is mapped to unregistered check {check_id!r}"
            )
    return problems


def check_evidence_consistency(
    check_results: dict[str, VerificationCheckResult],
    *,
    available_evidence_refs: set[str] | None = None,
) -> list[str]:
    """Return problems where results cite evidence that was never provided."""
    if available_evidence_refs is None:
        return []
    problems: list[str] = []
    for requirement_id, result in check_results.items():
        for ref in result.evidence_refs:
            if not ref or ref in available_evidence_refs:
                continue
            if ref.startswith(_SYNTHETIC_REF_PREFIXES):
                continue
            problems.append(
                f"{requirement_id}: evidence reference {ref!r} is not in the supplied evidence"
            )
    return problems


def _contradiction(
    kind: str, message: str, evidence_refs: Iterable[str] | None = None
) -> dict[str, Any]:
    return {
        "kind": kind,
        "message": message,
        "evidence_refs": [ref for ref in evidence_refs or [] if isinstance(ref, str) and ref],
    }


def detect_evidence_contradictions(bundle: EvidenceBundle) -> list[dict[str, Any]]:
    """Return explicit contradictions found in validated evidence.

    Only mutually exclusive observations are reported.  A mismatch between an
    expected value and an observed value is a *contract violation* handled by
    the deterministic checkers, not a contradiction, so it is not reported
    here.  An empty list means "no contradiction was found", never "the payload
    is proven correct".
    """
    contradictions: list[dict[str, Any]] = []

    # -- Episode: goal attainment recorded together with "not terminated".
    episode = bundle.episode if isinstance(bundle.episode, dict) else None
    if episode is not None:
        goal_attained = episode.get("goal_attained", episode.get("goal_reached"))
        terminated = episode.get("terminated")
        if goal_attained is True and terminated is False:
            contradictions.append(
                _contradiction(
                    "episode_goal_without_termination",
                    "Episode reports goal attainment but terminated=false",
                    bundle.episode_evidence_refs,
                )
            )

    # -- Events: one event ID recorded with two different event types.
    event_types: dict[str, Any] = {}
    for event in bundle.events or []:
        if not isinstance(event, dict):
            continue
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            continue
        event_type = event.get("event_type")
        if event_id in event_types and event_types[event_id] != event_type:
            contradictions.append(
                _contradiction(
                    "conflicting_duplicate_event",
                    f"event {event_id!r} is recorded with conflicting types "
                    f"{event_types[event_id]!r} and {event_type!r}",
                    [event_id],
                )
            )
        else:
            event_types.setdefault(event_id, event_type)

    # -- Metrics: same metric/episode/timestep recorded with different values.
    metric_values: dict[tuple[Any, Any, Any], tuple[float, str]] = {}
    for index, metric in enumerate(bundle.metrics or []):
        if not isinstance(metric, dict):
            continue
        name = metric.get("metric_name") or metric.get("name")
        if not isinstance(name, str) or not name:
            continue
        value = metric.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        episode_id = metric.get("episode_id")
        timestep = metric.get("timestep")
        # Without an identity key two records are merely two observations of the
        # same series; calling that a contradiction would be a false positive.
        if episode_id is None and timestep is None:
            continue
        key = (name, episode_id, timestep)
        ref = (
            metric.get("observation_id")
            or metric.get("id")
            or metric.get("metric_id")
            or f"metric[{index}]"
        )
        previous = metric_values.get(key)
        if previous is not None and previous[0] != float(value):
            contradictions.append(
                _contradiction(
                    "conflicting_duplicate_metric",
                    f"metric {name!r} is recorded with conflicting values "
                    f"{previous[0]:g} and {float(value):g} for the same "
                    "episode/timestep",
                    [str(ref), previous[1]],
                )
            )
        else:
            metric_values.setdefault(key, (float(value), str(ref)))

    # -- Configuration: the same key declared with different values.
    environment_config = bundle.environment_config or {}
    training_config = bundle.training_config or {}
    for key in sorted(set(environment_config) & set(training_config)):
        left = environment_config[key]
        right = training_config[key]
        if isinstance(left, (dict, list)) or isinstance(right, (dict, list)):
            continue
        if left != right:
            contradictions.append(
                _contradiction(
                    "configuration_conflict",
                    f"configuration key {key!r} is declared as {left!r} in the "
                    f"environment configuration and {right!r} in the training "
                    "configuration",
                    [f"config.{key}"],
                )
            )

    return contradictions


def check_verification_consistency(
    *,
    requirements: list[VerificationRequirement],
    check_results: dict[str, VerificationCheckResult],
    registered_checks: dict[str, str] | None = None,
    registered_tool_ids: set[str] | None = None,
    available_evidence_refs: set[str] | None = None,
    contradictions: list[dict[str, Any]] | None = None,
    evidence_available: bool | None = None,
) -> dict[str, Any]:
    """Run all consistency checks and return a structured summary.

    ``evidence_available`` distinguishes "no problems were found" from "there
    was no evidence to cross-check".  When it is ``False`` the summary reports
    ``not_evaluable`` and ``consistent`` is ``False`` so that a caller cannot
    present missing evidence as a clean result.
    """
    problems: list[str] = []
    problems.extend(validate_requirement_alignment(requirements, check_results))
    problems.extend(check_result_consistency(check_results))
    if registered_checks is not None and registered_tool_ids is not None:
        problems.extend(
            check_plan_consistency(
                requirements=requirements,
                registered_checks=registered_checks,
                registered_tool_ids=registered_tool_ids,
            )
        )
    problems.extend(
        check_evidence_consistency(
            check_results, available_evidence_refs=available_evidence_refs
        )
    )

    passing_unbacked = [
        requirement_id
        for requirement_id, result in check_results.items()
        if result.status is CheckStatus.PASS and not result.evidence_refs
    ]
    contradictions = list(contradictions or [])

    if evidence_available is False:
        status = "not_evaluable"
        consistent = False
    elif problems or passing_unbacked or contradictions:
        status = "contradictory" if contradictions else "inconsistent"
        consistent = False
    elif evidence_available is None:
        status = "unknown"
        consistent = not problems and not passing_unbacked
    else:
        status = "consistent"
        consistent = True

    return {
        "status": status,
        "consistent": consistent,
        "problems": problems,
        "contradictions": contradictions,
        "passing_without_evidence": passing_unbacked,
        "evidence_available": evidence_available,
    }


__all__ = [
    "check_evidence_consistency",
    "check_plan_consistency",
    "check_result_consistency",
    "check_verification_consistency",
    "detect_evidence_contradictions",
]
