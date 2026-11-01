"""Deterministic validation of verification results and model handoffs.

Two responsibilities:

1. **Result integrity.**  Reject result shapes that would let an unsupported
   claim pass as evidence-backed verification: a ``PASS`` without evidence
   references, a violation without any expected/actual value, or a check
   result that references a requirement that was never planned.
2. **Investigator handoff.**  Normalise and validate the advisory structure
   returned by a Meta AI provider.  A hypothesis is never promoted to a
   confirmed root cause without supporting evidence references.

Validation never rewrites a deterministic verdict.  Problems are returned as
strings so callers can surface them as warnings or block persistence.
"""

from __future__ import annotations

from typing import Any

from backend.verification.models import (
    AnomalyObservation,
    CheckStatus,
    VerificationCheckResult,
    VerificationRequirement,
    VerificationResult,
)

#: Minimum keys an investigator response must carry (interfaces.MetaAIProvider).
INVESTIGATION_REQUIRED_KEYS: tuple[str, ...] = (
    "summary",
    "observed_facts",
    "candidate_causes",
    "supporting_evidence",
    "contradicting_evidence",
    "root_cause_status",
    "recommended_tests",
    "limitations",
)

#: Allowed root-cause labels.  ``confirmed`` requires evidence references.
ROOT_CAUSE_STATUSES: frozenset[str] = frozenset(
    {"confirmed", "probable", "unresolved", "unknown"}
)


def validate_check_result(result: VerificationCheckResult) -> list[str]:
    """Return structural problems with a single check result."""
    problems: list[str] = []
    if not result.requirement_id:
        problems.append("check result has no requirement_id")
    if not isinstance(result.status, CheckStatus):
        problems.append("check result status is not a CheckStatus value")
        return problems

    evidence_refs = [ref for ref in result.evidence_refs if isinstance(ref, str) and ref]
    if result.status is CheckStatus.PASS and not evidence_refs:
        problems.append(
            f"{result.requirement_id}: PASS has no evidence reference"
        )
    if result.status is CheckStatus.FAIL and result.expected is None and result.actual is None:
        problems.append(
            f"{result.requirement_id}: FAIL records neither an expected nor an actual value"
        )
    if len(evidence_refs) != len(result.evidence_refs):
        problems.append(
            f"{result.requirement_id}: evidence_refs contains an empty or non-string entry"
        )
    return problems


def validate_anomaly(anomaly: AnomalyObservation) -> list[str]:
    """Return structural problems with an anomaly observation."""
    problems: list[str] = []
    if anomaly.score is not None and not 0.0 <= anomaly.score <= 1.0:
        problems.append("anomaly score is outside [0, 1]")
    if not anomaly.evidence_refs:
        problems.append("anomaly observation has no evidence reference")
    return problems


def validate_requirement_alignment(
    requirements: list[VerificationRequirement],
    check_results: dict[str, VerificationCheckResult],
) -> list[str]:
    """Check that results and requirements reference each other consistently."""
    problems: list[str] = []
    planned = {requirement.id for requirement in requirements}
    evaluated = set(check_results)

    for requirement_id in sorted(evaluated - planned):
        problems.append(
            f"check result for {requirement_id} has no corresponding requirement"
        )
    for requirement_id in sorted(planned - evaluated):
        problems.append(
            f"requirement {requirement_id} was planned but never evaluated"
        )

    for requirement_id, result in check_results.items():
        if result.requirement_id != requirement_id:
            problems.append(
                f"check result key {requirement_id} does not match "
                f"requirement_id {result.requirement_id}"
            )
    return problems


def validate_verification_result(result: VerificationResult) -> list[str]:
    """Return structural problems with an aggregated verification result."""
    problems: list[str] = []
    if not isinstance(result.overall_status, CheckStatus):
        problems.append("overall_status is not a CheckStatus value")
    for requirement_id, check_result in result.requirements.items():
        for problem in validate_check_result(check_result):
            problems.append(f"{requirement_id}: {problem}")
    if result.overall_status is CheckStatus.PASS and not result.evidence_refs:
        problems.append("overall PASS has no evidence reference")
    return problems


def validate_investigation_result(
    payload: Any,
) -> tuple[dict[str, Any], list[str]]:
    """Normalise an advisory investigator payload.

    Returns ``(normalised, problems)``.  Missing fields are reported, not
    invented.  A ``confirmed`` root cause without evidence references is
    downgraded to ``unresolved`` because deterministic verification, not the
    model, is authoritative.
    """
    problems: list[str] = []
    if not isinstance(payload, dict):
        return {}, ["investigator payload is not an object"]

    normalised: dict[str, Any] = {}
    for key in INVESTIGATION_REQUIRED_KEYS:
        if key not in payload:
            problems.append(f"investigator payload is missing {key!r}")

    summary = payload.get("summary")
    normalised["summary"] = summary if isinstance(summary, str) else ""

    for key in (
        "observed_facts",
        "candidate_causes",
        "supporting_evidence",
        "contradicting_evidence",
        "recommended_tests",
        "limitations",
    ):
        value = payload.get(key)
        if value is None:
            normalised[key] = []
        elif isinstance(value, list):
            normalised[key] = value
        else:
            problems.append(f"{key!r} must be a list")
            normalised[key] = []

    confidence = payload.get("confidence")
    if confidence is None:
        normalised["confidence"] = None
    elif isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and 0.0 <= float(confidence) <= 1.0:
        normalised["confidence"] = float(confidence)
    else:
        problems.append("'confidence' must be a number in [0, 1] or null")
        normalised["confidence"] = None

    root_cause_status = payload.get("root_cause_status")
    if not isinstance(root_cause_status, str) or not root_cause_status:
        problems.append("'root_cause_status' must be a non-empty string")
        normalised["root_cause_status"] = "unknown"
    elif root_cause_status not in ROOT_CAUSE_STATUSES:
        problems.append(
            f"unknown root_cause_status {root_cause_status!r}; treated as 'unresolved'"
        )
        normalised["root_cause_status"] = "unresolved"
    else:
        normalised["root_cause_status"] = root_cause_status

    if normalised["root_cause_status"] == "confirmed" and not normalised["supporting_evidence"]:
        problems.append(
            "'confirmed' root cause has no supporting evidence; downgraded to 'unresolved'"
        )
        normalised["root_cause_status"] = "unresolved"

    for key, value in payload.items():
        if key not in normalised:
            normalised[key] = value
    return normalised, problems


__all__ = [
    "INVESTIGATION_REQUIRED_KEYS",
    "ROOT_CAUSE_STATUSES",
    "validate_anomaly",
    "validate_check_result",
    "validate_investigation_result",
    "validate_requirement_alignment",
    "validate_verification_result",
]
