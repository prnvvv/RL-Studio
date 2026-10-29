"""Episode outcome verification checker.

Verifies episode-level requirements using actual episode evidence.

See ``backend/verification/tools/`` for the package README and integration notes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.verification.models import (
    VerificationCheckResult,
    VerificationRequirement,
    CheckStatus,
    RequirementType,
    EvidenceReference,
    MetricObservation,
)
from backend.verification.exceptions import InputValidationError, EvidenceUnavailableError


def _find_termination_event(
    episode_data: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Find the termination event in episode data, if present."""
    if episode_data is None:
        return None
    for key in ("terminated", "done", "status", "termination"):
        if key in episode_data:
            val = episode_data[key]
            if isinstance(val, bool):
                return {"key": key, "value": val}
            if isinstance(val, str) and val.lower() in ("true", "terminated", "yes"):
                return {"key": key, "value": True}
    return None


def _find_truncation_event(
    episode_data: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Find the truncation event in episode data, if present."""
    if episode_data is None:
        return None
    for key in ("truncated", "truncate", "truncation"):
        if key in episode_data:
            val = episode_data[key]
            if isinstance(val, bool):
                return {"key": key, "value": val}
            if isinstance(val, str) and val.lower() in ("true", "truncated", "yes"):
                return {"key": key, "value": True}
    return None


def _find_goal_attainment_event(
    episode_data: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Find goal attainment information in episode data, if present."""
    if episode_data is None:
        return None
    for key in ("goal_attained", "goal_reached", "goal_achieved", "success"):
        if key in episode_data:
            val = episode_data[key]
            if isinstance(val, bool):
                return {"key": key, "value": val}
            if isinstance(val, str) and val.lower() in ("true", "yes", "reached"):
                return {"key": key, "value": True}
    return None


def _make_details(note: str, source: Optional[str] = None) -> Dict[str, Any]:
    """Create a details dict compatible with VerificationCheckResult."""
    d: Dict[str, Any] = {"note": note}
    if source is not None:
        d["source"] = source
    return d


def execute_check(
    check_id: str,
    requirement: VerificationRequirement,
    *,
    episode_id: Optional[str] = None,
    episode_data: Optional[Dict[str, Any]] = None,
    termination_observed: Optional[bool] = None,
    truncation_observed: Optional[bool] = None,
    goal_attained_observed: Optional[bool] = None,
    source: str = "episode_check",
) -> VerificationCheckResult:
    """Execute an episode outcome verification check.

    Verifies episode-level requirements using actual episode evidence.

    Only the checks that can be established from actual available evidence are
    implemented.

    Args:
        check_id: Identifier for this check.
        requirement: The ``VerificationRequirement`` describing what is expected.
        episode_id: Optional episode identifier.
        episode_data: Optional full episode data dict.
        termination_observed: Optional boolean indicating if the episode
            terminated (as opposed to truncation).
        truncation_observed: Optional boolean indicating if the episode was
            truncated (time limit).
        goal_attained_observed: Optional boolean indicating if the goal was
            attained.
        source: Human-readable source label for evidence provenance.

    Returns:
        A ``VerificationCheckResult`` with status ``PASS``, ``FAIL``,
        ``UNKNOWN``, or ``BLOCKED``.
    """
    expected = requirement.expected_value
    evidence_parts: List[str] = []

    # Build a picture of what's available from explicit flags
    term_provided = termination_observed is not None
    trunc_provided = truncation_observed is not None
    goal_provided = goal_attained_observed is not None

    # Determine what to compare based on what's available
    if term_provided or trunc_provided or goal_provided:
        actual_status: Optional[str] = None

        if termination_observed is True:
            actual_status = "terminated"
        elif truncation_observed is True:
            actual_status = "truncated"
        elif goal_attained_observed is True:
            actual_status = "goal_attained"
        elif termination_observed is False:
            actual_status = "not_terminated"
        elif truncation_observed is False:
            actual_status = "not_truncated"
        elif goal_attained_observed is False:
            actual_status = "goal_not_attained"
        else:
            actual_status = "unknown"

        expected_status = str(expected) if expected is not None else None

        if expected_status and actual_status != "unknown":
            if expected_status == actual_status:
                status = "pass"
                description = f"expected={expected_status}, actual={actual_status}"
            else:
                status = "fail"
                description = f"expected={expected_status}, actual={actual_status}"
        else:
            status = "unknown"
            description = f"expected={expected_status}, actual={actual_status}"

        details = _make_details(description, source)

        from backend.verification.models import VerificationCheckResult

        result = VerificationCheckResult(
            requirement_id=requirement.id,
            status=status,
            expected=expected,
            actual=actual_status,
            tolerance=None,
            evidence_refs=evidence_parts,
            details=details,
        )

        # Add evidence parts
        result.evidence_refs.extend([f"episode:{p}" for p in evidence_parts])

        return result

    # If we have full episode_data, try to extract events from it and evaluate
    if episode_data is not None:
        term_event = _find_termination_event(episode_data)
        trunc_event = _find_truncation_event(episode_data)
        goal_event = _find_goal_attainment_event(episode_data)

        new_evidence_parts: List[str] = []
        if term_event is not None:
            new_evidence_parts.append(f"term_event:{term_event['key']}={term_event['value']}")
        if trunc_event is not None:
            new_evidence_parts.append(f"trunc_event:{trunc_event['key']}={trunc_event['value']}")
        if goal_event is not None:
            new_evidence_parts.append(f"goal_event:{goal_event['key']}={goal_event['value']}")

        evidence_parts.extend(new_evidence_parts)

        # Evaluate based on extracted events with correct semantics:
        # - Goal attainment takes priority
        # - If termination event found with True value AND no truncation (trunc event False or absent), it's terminated
        # - If truncation event found with True value, that's the status
        # - Otherwise unknown
        goal_found = goal_event is not None and goal_event["value"] is True
        term_found = term_event is not None and term_event["value"] is True
        trunc_found = trunc_event is not None and trunc_event["value"] is True

        # Actual status determination with correct semantics:
        # - If goal was attained, that's the status
        # - If episode terminated (term event found with True value) and was NOT truncated (trunc event False or absent), it's terminated
        # - If episode was truncated (trunc event found with True value), that's the status
        # - Otherwise unknown
        actual_status: Optional[str] = None
        if goal_found:
            actual_status = "goal_attained"
        elif term_found and not trunc_found:
            # Episode terminated and was not truncated
            actual_status = "terminated"
        elif trunc_found:
            # Episode was truncated
            actual_status = "truncated"
        else:
            actual_status = "unknown"

        expected_status = str(expected) if expected is not None else None

        # Map expected boolean to the corresponding status string for comparison.
        # expected_value=True for termination means "episode must terminate";
        # the actual status string for termination is "terminated".
        # expected_value=False means "episode must not terminate" / "episode must not
        # successfully terminate"; the actual status string for not-terminating is
        # "not_terminated".
        expected_status_mapped: Optional[str] = None
        if expected is True:
            expected_status_mapped = "terminated"
        elif expected is False:
            expected_status_mapped = "not_terminated"

        if expected_status and actual_status != "unknown":
            if expected_status_mapped is not None:
                # Compare using the mapped status string for boolean expectations.
                if expected_status_mapped == actual_status:
                    status = "pass"
                    description = f"expected={expected_status}, actual={actual_status}"
                else:
                    status = "fail"
                    description = f"expected={expected_status}, actual={actual_status}"
            elif expected_status == actual_status:
                # Fallback: direct string comparison (e.g. expected="pass", actual="pass")
                status = "pass"
                description = f"expected={expected_status}, actual={actual_status}"
            else:
                status = "fail"
                description = f"expected={expected_status}, actual={actual_status}"
        else:
            status = "unknown"
            description = f"expected={expected_status}, actual={actual_status}"

        details = _make_details(description, source)

        from backend.verification.models import VerificationCheckResult

        result = VerificationCheckResult(
            requirement_id=requirement.id,
            status=status,
            expected=expected,
            actual=actual_status,
            tolerance=None,
            evidence_refs=evidence_parts,
            details=details,
        )

        # Add evidence parts
        result.evidence_refs.extend([f"episode:{p}" for p in evidence_parts])

        return result

    # If we have no episode_data and no flags, return unknown
    if not term_provided and not trunc_provided and not goal_provided and episode_data is None:
        from backend.verification.models import VerificationCheckResult

        return VerificationCheckResult(
            requirement_id=requirement.id,
            status="unknown",
            expected=expected,
            actual=None,
            tolerance=None,
            evidence_refs=[],
            details=_make_details("No episode evidence provided and no termination/truncation/goal flags available", source),
        )

    # We have some evidence; return a result based on what we know.
    # If we have a determined status, use it; otherwise unknown.
    if "status" in dir() and "status" in dir():
        pass

    # Fall back to unknown
    from backend.verification.models import VerificationCheckResult

    return VerificationCheckResult(
        requirement_id=requirement.id,
        status="unknown",
        expected=expected,
        actual=None,
        tolerance=None,
        evidence_refs=evidence_parts,
        details=_make_details("Episode evidence partially available; see evidence_refs for details", source),
    )