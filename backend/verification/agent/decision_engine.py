"""Authoritative verification decision engine.

Determines the overall verification status from per-requirement check results.
Pure deterministic logic — LLM output must not influence the decision.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional, Set

from backend.verification.models import VerificationCheckResult, VerificationRequirement, CheckStatus
from backend.verification.exceptions import InputValidationError


# ---------------------------------------------------------------------------
# Status aggregation rules (deterministic, total function)
# ---------------------------------------------------------------------------

# Which statuses are "mandatory" — if any mandatory check fails or is
# unverifiable, the overall result cannot be PASS.
MANDATORY_STATUSES: FrozenSet[CheckStatus] = frozenset({
    CheckStatus.PASS,
    CheckStatus.FAIL,
    CheckStatus.UNKNOWN,
})

# Statuses that, when present as a requirement result, block PASS.
BLOCKING_STATUSES: FrozenSet[CheckStatus] = frozenset({
    CheckStatus.FAIL,
    CheckStatus.ERROR,
})


def _classify_result(result: VerificationCheckResult) -> Dict[str, Any]:
    """Classify a single requirement check result.

    Returns a dict with:
    - "status": the check status
    - "mandatory": whether this requirement is mandatory (has no optional flags)
    - "has_evidence": whether evidence references are present
    """
    status = result.status
    evidence_refs = getattr(result, "evidence_refs", []) or []
    has_evidence = bool(evidence_refs)

    # A requirement is "mandatory" when it has no optional markers.
    # For now, treat all requirements as mandatory unless future
    # metadata indicates otherwise.
    is_mandatory = True

    return {
        "status": status,
        "mandatory": is_mandatory,
        "has_evidence": has_evidence,
    }


def aggregate_results(
    requirements: Dict[str, VerificationCheckResult],
    *,
    enforce_mandatory: bool = True,
) -> Dict[str, Any]:
    """Aggregate per-requirement check results into an overall verification result.

    Aggregation rules (deterministic, no LLM influence):

    1. If any mandatory requirement has status FAIL → overall FAIL.
    2. If any mandatory requirement has status ERROR → overall ERROR.
    3. If any mandatory requirement has status UNKNOWN and no evidence → overall UNKNOWN.
    4. Otherwise → overall PASS.

    The ``enforce_mandatory`` flag controls whether missing/unknown mandatory
    checks block PASS.  Set False only for non-critical evaluation scenarios.

    Returns a dict with:
    - "overall_status": one of PASS, FAIL, ERROR, UNKNOWN
    - "requirements": mapped statuses per requirement ID
    - "details": human-readable summary
    """
    if not requirements:
        return {
            "overall_status": CheckStatus.UNKNOWN,
            "requirements": {},
            "details": "No requirements provided for aggregation.",
        }

    # Classify each requirement result
    classified: Dict[str, Dict[str, Any]] = {}
    for req_id, result in requirements.items():
        classified[req_id] = _classify_result(result)

    # Determine overall status
    # Check for blocking statuses among mandatory requirements
    has_fail = False
    has_error = False
    mandatory_unknown_no_evidence = False

    for req_id, cls in classified.items():
        status = cls["status"]
        is_mand = cls["mandatory"]

        # Use == comparison for CheckStatus enums (more robust than isinstance
        # across different import paths or enum redefinitions).
        if is_mand and status.value == CheckStatus.FAIL.value:
            has_fail = True
        if is_mand and status.value == CheckStatus.ERROR.value:
            has_error = True
        if is_mand and status.value == CheckStatus.UNKNOWN.value and not cls["has_evidence"]:
            mandatory_unknown_no_evidence = True

    # Apply aggregation rules
    if has_fail:
        overall = CheckStatus.FAIL
    elif has_error:
        overall = CheckStatus.ERROR
    elif mandatory_unknown_no_evidence:
        overall = CheckStatus.UNKNOWN
    else:
        overall = CheckStatus.PASS

    # Build per-requirement status map
    req_status_map: Dict[str, str] = {}
    for req_id, cls in classified.items():
        req_status_map[req_id] = cls["status"]

    # Construct human-readable details
    failing_reqs = [
        rid for rid, cls in classified.items()
        if cls["mandatory"] and cls["status"].value in {CheckStatus.FAIL.value, CheckStatus.ERROR.value}
    ]
    unknown_no_ev = [
        rid for rid, cls in classified.items()
        if cls["mandatory"] and cls["status"].value == CheckStatus.UNKNOWN.value
        and not cls["has_evidence"]
    ]

    detail_parts = []
    if failing_reqs:
        detail_parts.append(
            f"Mandatory requirement{'s' if len(failing_reqs) > 1 else ''} "
            f"{' '.join(failing_reqs)} failed or errored."
        )
    if unknown_no_ev:
        detail_parts.append(
            f"Mandatory requirement{'s' if len(unknown_no_ev) > 1 else ''} "
            f"{' '.join(unknown_no_ev)} have no available evidence."
        )
    if not failing_reqs and not unknown_no_ev:
        detail_parts.append("All mandatory requirements passed with available evidence.")
    details = " ".join(detail_parts)

    return {
        "overall_status": overall,
        "requirements": req_status_map,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decide(
    input_data: VerificationInput,
    context: VerificationContext,
    check_results: Dict[str, VerificationCheckResult],
    *,
    enforce_mandatory: bool = True,
) -> Dict[str, Any]:
    """Decide the overall verification status from check results.

    This is the authoritative decision point.  LLM output may describe
    findings but must not override the deterministic result.

    Args:
        input_data: The original verification input.
        context: The verification runtime context.
        check_results: Map from requirement ID to VerificationCheckResult.
        enforce_mandatory: When True (default), mandatory FAIL/ERROR/UNKNOWN
            without evidence blocks overall PASS.

    Returns:
        A dict with ``overall_status``, per-``requirements`` statuses, and
        ``details`` string.
    """
    # Aggregate using deterministic rules
    aggregated = aggregate_results(
        {str(k): v for k, v in check_results.items()},
        enforce_mandatory=enforce_mandatory,
    )

    # Ensure the overall status is a CheckStatus enum value
    overall = aggregated["overall_status"]
    if not isinstance(overall, CheckStatus):
        try:
            overall = CheckStatus(overall)
        except (ValueError, TypeError):
            overall = CheckStatus.UNKNOWN

    return {
        "overall_status": overall,
        "requirements": aggregated["requirements"],
        "details": aggregated["details"],
        "input_id": getattr(input_data, "agent_metadata", None)
        and getattr(input_data.agent_metadata, "agent_id", None),
        "context_id": getattr(context, "run_identifier", None)
        if context
        else None,
    }
