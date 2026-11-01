"""Aggregation of per-requirement check results.

This module is a thin, typed facade over the authoritative decision engine in
``backend.verification.agent.decision_engine``.  It does **not** re-implement
status precedence: having two aggregation implementations would risk the
deterministic verdict diverging between callers.

Only deterministic inputs are used.  Model output is never accepted here.
"""

from __future__ import annotations

from typing import Any

from backend.verification.agent.decision_engine import aggregate_results
from backend.verification.models import (
    CheckStatus,
    VerificationCheckResult,
    VerificationRequirement,
    VerificationResult,
)


def mandatory_map(
    requirements: list[VerificationRequirement] | None,
) -> dict[str, bool]:
    """Return ``{requirement_id: is_mandatory}`` for the given requirements."""
    return {
        requirement.id: requirement.is_mandatory
        for requirement in (requirements or [])
    }


def aggregate_check_results(
    check_results: dict[str, VerificationCheckResult],
    *,
    requirements: list[VerificationRequirement] | None = None,
) -> dict[str, Any]:
    """Aggregate check results into an overall status.

    The mandatory designation comes from the originating requirement when it is
    known, otherwise from the check result itself.
    """
    return aggregate_results(
        dict(check_results),
        req_is_mandatory=mandatory_map(requirements) or None,
    )


def build_verification_result(
    check_results: dict[str, VerificationCheckResult],
    *,
    requirements: list[VerificationRequirement] | None = None,
    summary: str | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> VerificationResult:
    """Assemble a canonical ``VerificationResult`` model.

    Evidence references are the union of real identifiers attached to the
    individual check results; nothing is synthesised.
    """
    aggregated = aggregate_check_results(check_results, requirements=requirements)
    overall = aggregated["overall_status"]
    if not isinstance(overall, CheckStatus):
        overall = CheckStatus.UNKNOWN

    evidence_refs: list[str] = []
    for result in check_results.values():
        for ref in result.evidence_refs:
            if isinstance(ref, str) and ref and ref not in evidence_refs:
                evidence_refs.append(ref)

    return VerificationResult(
        overall_status=overall,
        requirements=dict(check_results),
        summary=summary if summary is not None else aggregated["details"],
        evidence_refs=evidence_refs,
        warnings=list(warnings or []),
        errors=list(errors or []),
    )


__all__ = [
    "aggregate_check_results",
    "build_verification_result",
    "mandatory_map",
]
