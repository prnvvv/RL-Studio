"""Assembly of human-facing verification reports.

A report packages an already-computed deterministic ``VerificationResult``
together with an optional advisory diagnosis.  It must never upgrade a
non-PASS verification, invent recommendations, or present a model hypothesis as
a confirmed root cause.
"""

from __future__ import annotations

from typing import Any

from backend.verification.models import (
    CheckStatus,
    VerificationReport,
    VerificationResult,
)


def _status_label(status: CheckStatus) -> str:
    return status.value if isinstance(status, CheckStatus) else str(status)


def build_summary(result: VerificationResult) -> str:
    """Return a factual, one-paragraph summary of a verification result."""
    total = len(result.requirements)
    if total == 0:
        return "No requirement results were produced; the outcome is not evaluable."
    counts: dict[str, int] = {}
    for check_result in result.requirements.values():
        label = _status_label(check_result.status)
        counts[label] = counts.get(label, 0) + 1
    breakdown = ", ".join(f"{label}={count}" for label, count in sorted(counts.items()))
    return (
        f"Overall status: {_status_label(result.overall_status)}. "
        f"{total} requirement(s) evaluated ({breakdown})."
    )


def build_report(
    result: VerificationResult,
    *,
    diagnosis: dict[str, Any] | None = None,
    recommendations: list[str] | None = None,
    limitations: list[str] | None = None,
    summary: str | None = None,
) -> VerificationReport:
    """Build a ``VerificationReport`` from a verification result.

    Recommendations are only carried through when they were supplied
    explicitly.  When the diagnosis failed or is unavailable, that fact is
    recorded as a limitation instead of being hidden.
    """
    report_limitations: list[str] = list(limitations or [])

    if diagnosis is not None:
        status = diagnosis.get("status")
        if status and status != "completed":
            report_limitations.append(
                f"Meta AI investigation status: {status}; no advisory analysis is included."
            )
        elif status == "completed":
            result_payload = diagnosis.get("result")
            if isinstance(result_payload, dict):
                for limitation in result_payload.get("limitations") or []:
                    if isinstance(limitation, str) and limitation not in report_limitations:
                        report_limitations.append(limitation)
                if result_payload.get("root_cause_status") != "confirmed":
                    report_limitations.append(
                        "No root cause was confirmed; candidate causes are hypotheses."
                    )

    if result.overall_status is not CheckStatus.PASS:
        report_limitations.append(
            "The verification did not pass; see per-requirement results before acting."
        )

    evidence_refs: list[str] = list(result.evidence_refs)
    if diagnosis is not None and isinstance(diagnosis.get("result"), dict):
        for fact in diagnosis["result"].get("observed_facts") or []:
            if isinstance(fact, dict):
                for ref in fact.get("evidence_refs") or []:
                    if isinstance(ref, str) and ref and ref not in evidence_refs:
                        evidence_refs.append(ref)

    return VerificationReport(
        verification=result,
        summary=summary if summary is not None else build_summary(result),
        recommendations=list(recommendations or []),
        limitations=report_limitations,
        evidence_refs=evidence_refs,
    )


__all__ = ["build_report", "build_summary"]
