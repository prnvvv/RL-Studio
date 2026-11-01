"""Cross-check consistency of verification plans, results, and evidence.

The consistency checker answers one question: *is this verification payload
internally coherent?*  It does not decide pass/fail (the decision engine does)
and it does not call a model.  Its output is a list of problem strings that
callers surface as warnings or use to block persistence.
"""

from __future__ import annotations

from typing import Any

from backend.verification.models import (
    CheckStatus,
    VerificationCheckResult,
    VerificationRequirement,
)
from backend.verification.result_validator import (
    validate_check_result,
    validate_requirement_alignment,
)


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
            if ref and ref not in available_evidence_refs:
                problems.append(
                    f"{requirement_id}: evidence reference {ref!r} is not in the supplied evidence"
                )
    return problems


def check_verification_consistency(
    *,
    requirements: list[VerificationRequirement],
    check_results: dict[str, VerificationCheckResult],
    registered_checks: dict[str, str] | None = None,
    registered_tool_ids: set[str] | None = None,
    available_evidence_refs: set[str] | None = None,
) -> dict[str, Any]:
    """Run all consistency checks and return a structured summary."""
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
    return {
        "consistent": not problems and not passing_unbacked,
        "problems": problems,
        "passing_without_evidence": passing_unbacked,
    }


__all__ = [
    "check_evidence_consistency",
    "check_plan_consistency",
    "check_result_consistency",
    "check_verification_consistency",
]
