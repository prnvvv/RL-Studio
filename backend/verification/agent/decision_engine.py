"""Authoritative verification decision engine.

Determines the overall verification status from per-requirement check results.
Pure deterministic logic — LLM output must not influence the decision.

All aggregation is a total function over the status lattice:
  PASS > FAIL, ERROR, UNKNOWN, BLOCKED, PENDING
Only PASS produces overall PASS.  Every other status blocks PASS
when it is mandatory or when insufficient evidence is available.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Optional

from backend.verification.models import VerificationCheckResult, CheckStatus, VerificationInput, VerificationContext
from backend.verification.exceptions import InputValidationError


# ---------------------------------------------------------------------------
# Canonical status lattice: only PASS yields overall PASS.
# Every other status, when present as a mandatory requirement result,
# prevents PASS.  The ``enforce_mandatory`` flag controls whether
# missing evidence on an otherwise-OK check also blocks PASS.
# ---------------------------------------------------------------------------

# All known CheckStatus values.  Explicit enumeration so that new status
# additions are visible at module load time and do not silently change
# aggregation behaviour.
ALL_STATUSES: FrozenSet[CheckStatus] = frozenset({
    CheckStatus.PASS,
    CheckStatus.FAIL,
    CheckStatus.ERROR,
    CheckStatus.UNKNOWN,
    CheckStatus.BLOCKED,
    CheckStatus.PENDING,
})

# Which statuses, if any, can ever contribute to an overall PASS.
# Only PASS itself; every other status blocks PASS when mandatory.
PASSIBLE_FOR_OVERALL_PASS: FrozenSet[CheckStatus] = frozenset({
    CheckStatus.PASS,
})

# Which statuses, when present as a mandatory requirement result, unconditionally
# prevent overall PASS.  All non-PASS statuses block PASS when mandatory.
BLOCKING_FOR_PASS: FrozenSet[CheckStatus] = frozenset({
    CheckStatus.FAIL,
    CheckStatus.ERROR,
    CheckStatus.UNKNOWN,
    CheckStatus.BLOCKED,
    CheckStatus.PENDING,
})


# ---------------------------------------------------------------------------
# Classification of a single requirement check result.
# ---------------------------------------------------------------------------

def _classify_result(
    result: VerificationCheckResult,
    *,
    req_is_mandatory: Optional[bool] = None,
) -> Dict[str, Any]:
    """Classify a single requirement check result.

    Returns a dict with:
    - "status": the check status
    - "mandatory": whether this requirement is mandatory.
      If *req_is_mandatory* is provided, it overrides the result's
      ``is_mandatory`` default, allowing the caller to respect the
      requirement's actual designation.
    - "has_evidence": whether evidence references are present
    """
    status = result.status
    evidence_refs = getattr(result, "evidence_refs", []) or []
    has_evidence = bool(evidence_refs)

    # Use the explicitly provided mandatory designation if given,
    # otherwise fall back to the result's is_mandatory (which defaults
    # to True in the model but should be set by checkers from the
    # corresponding VerificationRequirement).
    is_mandatory = req_is_mandatory if req_is_mandatory is not None else getattr(result, "is_mandatory", True)

    return {
        "status": status,
        "mandatory": is_mandatory,
        "has_evidence": has_evidence,
    }


# ---------------------------------------------------------------------------
# Aggregation: deterministic, total function over per-requirement results.
# ---------------------------------------------------------------------------

def aggregate_results(
    requirements: Dict[str, VerificationCheckResult],
    *,
    enforce_mandatory: bool = True,
    req_is_mandatory: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """Aggregate per-requirement check results into an overall verification result.

    Aggregation rules (deterministic, no LLM influence):

    1. If any mandatory requirement has status FAIL → overall FAIL.
    2. If any mandatory requirement has status ERROR → overall ERROR.
    3. If any mandatory requirement has status BLOCKED → overall BLOCKED.
    4. If any mandatory requirement has status PENDING → overall PENDING.
    5. If any mandatory requirement has status UNKNOWN and no evidence → overall UNKNOWN.
    6. If every mandatory requirement has status PASS and available evidence → overall PASS.
    7. Otherwise → overall UNKNOWN.

    The ``enforce_mandatory`` flag controls whether missing/unknown mandatory
    checks (rule 5) block PASS when no FAIL/ERROR/BLOCKED/PENDING is present.
    Set False only for non-critical evaluation scenarios where a default PASS
    is acceptable in the face of incomplete evidence.

    Args:
        requirements: Map from requirement ID to VerificationCheckResult.
        enforce_mandatory: When True (default), mandatory FAIL/ERROR/UNKNOWN
            without evidence blocks overall PASS.
        req_is_mandatory: Optional dict mapping requirement ID to the
            requirement's actual mandatory designation.  If provided, these
            values override the ``is_mandatory`` field on the check results,
            allowing the aggregation to respect the requirement's true
            mandatory/optional designation rather than relying on the
            check result's default.

    Returns a dict with:
    - "overall_status": one of PASS, FAIL, ERROR, UNKNOWN, BLOCKED, PENDING
    - "requirements": mapped statuses per requirement ID
    - "details": human-readable summary
    """
    if not requirements:
        return {
            "overall_status": CheckStatus.UNKNOWN,
            "requirements": {},
            "details": "No requirements provided for aggregation.",
        }

    # Validate inputs: check that all values are VerificationCheckResult instances
    for req_id, result in requirements.items():
        if not isinstance(result, VerificationCheckResult):
            raise InputValidationError(
                f"Invalid check result for requirement {req_id!r}: expected VerificationCheckResult, got {type(result).__name__}"
            )

    # Classify each requirement result
    classified: Dict[str, Dict[str, Any]] = {}
    for req_id, result in requirements.items():
        # Get the requirement's actual mandatory designation, if provided
        mand = req_is_mandatory.get(req_id) if req_is_mandatory else None
        classified[req_id] = _classify_result(result, req_is_mandatory=mand)

    # Scan for blocking statuses among mandatory requirements.
    # Priority order: FAIL > ERROR > BLOCKED > PENDING > UNKNOWN(w/o evidence)
    has_fail = False
    has_error = False
    has_blocked = False
    has_pending = False
    mandatory_unknown_no_evidence = False
    all_mandatory_pass = True
    all_mandatory_have_evidence = True

    for req_id, cls in classified.items():
        status = cls["status"]
        is_mand = cls["mandatory"]
        has_ev = cls["has_evidence"]

        if is_mand and status.value == CheckStatus.FAIL.value:
            has_fail = True
        if is_mand and status.value == CheckStatus.ERROR.value:
            has_error = True
        if is_mand and status.value == CheckStatus.BLOCKED.value:
            has_blocked = True
        if is_mand and status.value == CheckStatus.PENDING.value:
            has_pending = True
        if is_mand and status.value == CheckStatus.UNKNOWN.value and not has_ev:
            mandatory_unknown_no_evidence = True
        if is_mand and status != CheckStatus.PASS:
            all_mandatory_pass = False
        if is_mand and not has_ev:
            all_mandatory_have_evidence = False

    # Apply aggregation rules in priority order
    if has_fail:
        overall = CheckStatus.FAIL
    elif has_error:
        overall = CheckStatus.ERROR
    elif has_blocked:
        overall = CheckStatus.BLOCKED
    elif has_pending:
        overall = CheckStatus.PENDING
    elif mandatory_unknown_no_evidence:
        overall = CheckStatus.UNKNOWN
    elif all_mandatory_pass and all_mandatory_have_evidence:
        overall = CheckStatus.PASS
    else:
        # Some mandatory requirement is not PASS but also not FAIL/ERROR/BLOCKED/PENDING/UNKNOWN-no-evidence.
        # This catches edge cases (e.g. a non-mandatory unknown with evidence, or an unexpected status).
        overall = CheckStatus.UNKNOWN

    # Build per-requirement status map
    req_status_map: Dict[str, str] = {}
    for req_id, cls in classified.items():
        req_status_map[req_id] = cls["status"]

    # Construct human-readable details
    failing_reqs = [
        rid for rid, cls in classified.items()
        if cls["mandatory"] and cls["status"].value in {CheckStatus.FAIL.value, CheckStatus.ERROR.value}
    ]
    blocked_reqs = [
        rid for rid, cls in classified.items()
        if cls["mandatory"] and cls["status"].value == CheckStatus.BLOCKED.value
    ]
    pending_reqs = [
        rid for rid, cls in classified.items()
        if cls["mandatory"] and cls["status"].value == CheckStatus.PENDING.value
    ]
    unknown_no_ev = [
        rid for rid, cls in classified.items()
        if cls["mandatory"] and cls["status"].value == CheckStatus.UNKNOWN.value
        and not cls["has_evidence"]
    ]
    pass_reqs = [
        rid for rid, cls in classified.items()
        if cls["mandatory"] and cls["status"].value == CheckStatus.PASS.value
        and cls["has_evidence"]
    ]

    detail_parts = []
    if failing_reqs:
        detail_parts.append(
            f"Mandatory requirement{'s' if len(failing_reqs) > 1 else ''} "
            f"{' '.join(failing_reqs)} failed or errored."
        )
    if blocked_reqs:
        detail_parts.append(
            f"Mandatory requirement{'s' if len(blocked_reqs) > 1 else ''} "
            f"{' '.join(blocked_reqs)} blocked."
        )
    if pending_reqs:
        detail_parts.append(
            f"Mandatory requirement{'s' if len(pending_reqs) > 1 else ''} "
            f"{' '.join(pending_reqs)} pending."
        )
    if unknown_no_ev:
        detail_parts.append(
            f"Mandatory requirement{'s' if len(unknown_no_ev) > 1 else ''} "
            f"{' '.join(unknown_no_ev)} have no available evidence."
        )
    if pass_reqs and not any([failing_reqs, blocked_reqs, pending_reqs, unknown_no_ev]):
        detail_parts.append("All mandatory requirements passed with available evidence.")

    details = " ".join(detail_parts) if detail_parts else "No requirement outcomes could be determined."

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
    req_is_mandatory: Optional[Dict[str, bool]] = None,
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
        req_is_mandatory: Optional dict mapping requirement ID to the
            requirement's actual mandatory designation.  If provided, these
            values override the ``is_mandatory`` field on the check results,
            allowing the aggregation to respect the requirement's true
            mandatory/optional designation rather than relying on the
            check result's default.

    Returns:
        A dict with ``overall_status``, per-``requirements`` statuses, and
        ``details`` string.
    """
    # Aggregate using deterministic rules
    aggregated = aggregate_results(
        {str(k): v for k, v in check_results.items()},
        enforce_mandatory=enforce_mandatory,
        req_is_mandatory=req_is_mandatory,
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
