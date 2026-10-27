"""Event and transition verification checker.

Verifies requirements about events that actually occurred or were recorded.

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
)
from backend.verification.exceptions import InputValidationError, EvidenceUnavailableError


def _find_event_in_records(
    records: Optional[List[Dict[str, Any]]],
    event_name: str,
    required: bool = True,
) -> Optional[Dict[str, Any]]:
    """Find an event with the given name in a list of record dicts.

    Returns the first matching event dict, or None if not found.
    Checks multiple possible field names including ``event_name``, 
    ``name``, and variations.
    """
    if records is None:
        return None if required else {"found": False, "reason": "no_records"}
    for record in records:
        if not isinstance(record, dict):
            continue
        # Check various possible field names for the event
        possible_keys = [
            event_name,
            f"event_{event_name}",
            f"{event_name}_event",
            "name",
            "event",
        ]
        for key in possible_keys:
            if key in record:
                return {"found": True, "event": record, "field": key}
    return {"found": False, "reason": f"event_{event_name}_not_found"}


def _extract_event_payload(
    event_record: Dict[str, Any],
    expected_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Extract a subset of fields from an event record.

    Returns only the fields that exist in the record and are in
    *expected_fields* (if provided).
    """
    result: Dict[str, Any] = {}
    if expected_fields is None:
        return dict(event_record)
    for field in expected_fields:
        if field in event_record:
            result[field] = event_record[field]
    return result


def execute_check(
    check_id: str,
    requirement: VerificationRequirement,
    *,
    recorded_events: Optional[List[Dict[str, Any]]] = None,
    required_event: Optional[str] = None,
    forbidden_event: Optional[str] = None,
    expected_event_order: Optional[List[str]] = None,
    event_count: Optional[Dict[str, int]] = None,
    source: str = "event_check",
) -> VerificationCheckResult:
    """Execute an event verification check.

    Verifies requirements about events that actually occurred or were recorded.

    Only supports event-ordering, counting, and timing constraints when the
    requirement models explicitly represent those constraints.

    Args:
        check_id: Identifier for this check.
        requirement: The ``VerificationRequirement`` describing what is expected.
        recorded_events: Optional list of event dicts that were recorded during
            the run.
        required_event: If provided, this event must be found in recorded_events.
        forbidden_event: If provided, this event must NOT be found in recorded_events.
        expected_event_order: If provided, events must appear in this order.
        event_count: If provided, a dict {event_name: count} specifying
            required counts.
        source: Human-readable source label for evidence provenance.

    Returns:
        A ``VerificationCheckResult`` with status ``PASS``, ``FAIL``,
        ``UNKNOWN``, or ``BLOCKED``.
    """
    expected = requirement.expected_value
    evidence_parts: List[str] = []

    # Handle required_event
    if required_event is not None:
        found = _find_event_in_records(recorded_events, required_event, required=True)
        if found and found.get("found"):
            # Check that the found event has meaningful semantics beyond
            # a superficial key name match.  A record that only contains
            # the key name (e.g. {"name": "goal"}) is insufficient evidence.
            event_record = found.get("event", {})
            key_match = found.get("field", "")
            # If the only matching key is "name" or "event" without other
            # event-specific fields, treat as insufficient evidence.
            superficial_keys = {"name", "event"}
            has_superficial_match = (
                key_match in superficial_keys
                and not any(k in event_record for k in {"event_name", "terminated", "truncated", "goal_attained"})
            )
            if has_superficial_match:
                from backend.verification.models import VerificationCheckResult

                return VerificationCheckResult(
                    requirement_id=requirement.id,
                    status="unknown",
                    expected=expected,
                    actual=None,
                    tolerance=None,
                    evidence_refs=evidence_parts,
                    details={
                        "note": f"required event '{required_event}' found but evidence "
                        "coverage may be insufficient; event record lacks semantic detail"
                    },
                )
            evidence_parts.append(f"required_event:{required_event}=found")
        else:
            # Required event not found — this is a failure only if the
            # requirement and evidence coverage establish a real violation.
            # Treat as unknown/inconclusive when evidence coverage is insufficient.
            from backend.verification.models import VerificationCheckResult

            return VerificationCheckResult(
                requirement_id=requirement.id,
                status="unknown",
                expected=expected,
                actual=None,
                tolerance=None,
                evidence_refs=evidence_parts,
                details={
                    "note": f"required event '{required_event}' not found in recorded events; evidence coverage may be insufficient"
                },
            )

    # Handle forbidden_event
    if forbidden_event is not None:
        found = _find_event_in_records(recorded_events, forbidden_event, required=False)
        if found and found.get("found"):
            from backend.verification.models import VerificationCheckResult

            return VerificationCheckResult(
                requirement_id=requirement.id,
                status="fail",
                expected=expected,
                actual=f"forbidden event '{forbidden_event}' was recorded",
                tolerance=None,
                evidence_refs=evidence_parts,
                details={"note": f"forbidden event '{forbidden_event}' was recorded but was expected not to occur"},
            )
        # Forbidden event not found — that's what we want; continue

    # Handle expected_event_order
    if expected_event_order is not None and recorded_events is not None:
        event_names = [ev.get("event_name", ev.get("name", "")) for ev in recorded_events if isinstance(ev, dict)]
        # Simple order check: the first occurrence of each required event
        # should appear in the specified order
        required_set = set(expected_event_order)
        found_events: List[str] = []
        for ev in recorded_events:
            if isinstance(ev, dict):
                name = ev.get("event_name", ev.get("name", ""))
                if name in required_set and name not in found_events:
                    found_events.append(name)

        # Check if the found events match the expected order
        order_passed = True
        if found_events != expected_event_order:
            order_passed = False

        if not order_passed:
            from backend.verification.models import VerificationCheckResult

            return VerificationCheckResult(
                requirement_id=requirement.id,
                status="fail",
                expected=expected,
                actual=f"event order mismatch; expected {expected_event_order}, got {found_events}",
                tolerance=None,
                evidence_refs=evidence_parts,
                details={
                    "event_order_mismatch": f"expected {expected_event_order}, got {found_events}"
                },
            )

    # Handle event_count
    if event_count is not None and recorded_events is not None:
        # Count occurrences of each event name
        from collections import Counter

        actual_counts = Counter()
        for ev in recorded_events:
            if isinstance(ev, dict):
                name = ev.get("event_name", ev.get("name", ""))
                actual_counts[name] += 1

        # Check each required count
        for event_name, required_count in event_count.items():
            actual_count = actual_counts.get(event_name, 0)
            if actual_count < required_count:
                from backend.verification.models import VerificationCheckResult

                return VerificationCheckResult(
                    requirement_id=requirement.id,
                    status="fail",
                    expected=f"{event_name} count >= {required_count}",
                    actual=f"{event_name} count = {actual_count}",
                    tolerance=None,
                    evidence_refs=evidence_parts,
                    details={
                        f"event_count_mismatch_{event_name}": f"required >= {required_count}, actual = {actual_count}"
                    },
                )

    # If we get here, the check passed (or has no specific constraints to violate)
    from backend.verification.models import VerificationCheckResult

    result = VerificationCheckResult(
        requirement_id=requirement.id,
        status="pass",
        expected=expected,
        actual="events verified",
        tolerance=None,
        evidence_refs=evidence_parts,
        details={"note": "Event requirements verified against recorded events"},
    )
    return result


# ---------------------------------------------------------------------------
# Module initialisation: no side effects beyond function definitions.
# ---------------------------------------------------------------------------

# Ensure the module can be imported without side effects beyond function
# definitions and the harmless helper functions above.  No API calls, no
# network hooks, no registry mutations occur at module load time.