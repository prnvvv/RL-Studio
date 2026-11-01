"""Event and transition verification checker.

Verifies requirements about events that were actually recorded during a run.

Non-negotiable rules (AGENTS.md §4.4, §6):

* An absent required event is a ``FAIL`` **only** when the caller asserts the
  evidence is complete.  Otherwise the result is ``UNKNOWN``.
* A check with no usable constraint is ``UNKNOWN``, never ``PASS``.
* ``PASS`` requires at least one satisfied constraint backed by real recorded
  events.
* Only real evidence identifiers are attached to the result.
"""

from __future__ import annotations

from typing import Any

from backend.verification.models import (
    CheckStatus,
    VerificationCheckResult,
    VerificationRequirement,
)

#: Keys that may carry an event name.
_NAME_KEYS = ("event_name", "name", "event_type", "event")

#: Fields whose presence means the record carries semantic event detail.
_SEMANTIC_FIELDS = ("timestep", "timestamp", "episode_id", "run_id", "payload")


def _event_name(record: dict[str, Any]) -> str | None:
    """Extract a normalised event name from a recorded event dict."""
    for key in _NAME_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _event_ref(record: dict[str, Any]) -> str | None:
    """Return the record's real evidence identifier, if it has one."""
    for key in ("event_id", "id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _deduplicate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop repeated deliveries of the same event ID, keeping first occurrence.

    The event stream may be delivered more than once (retries, reconnect
    replay).  Counting or matching duplicates would let a single violation
    occur "twice" or make a count requirement pass on repeated copies, so
    records are deduplicated by their real identifier.  Records without an
    identifier cannot be proven duplicates and are therefore kept.
    """
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            unique.append(record)
            continue
        ref = _event_ref(record)
        if ref is None:
            unique.append(record)
            continue
        if ref in seen:
            continue
        seen.add(ref)
        unique.append(record)
    return unique


def _collect_refs(
    records: list[dict[str, Any]] | None,
    names: set[str],
    *,
    limit: int,
) -> list[str]:
    """Collect real evidence identifiers for events named in *names*."""
    refs: list[str] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        name = _event_name(record)
        if name not in names:
            continue
        ref = _event_ref(record)
        if ref is not None and ref not in refs:
            refs.append(ref)
            if len(refs) >= limit:
                break
    return refs


def _find_record(
    records: list[dict[str, Any]] | None,
    event_name: str,
) -> dict[str, Any] | None:
    """Return the first recorded event matching *event_name*."""
    for record in records or []:
        if isinstance(record, dict) and _event_name(record) == event_name:
            return record
    return None


def _occurred(record: dict[str, Any] | None) -> bool:
    """Return True when *record* represents an event that actually occurred.

    A record whose only content is a ``False`` flag does not evidence an
    occurrence, and a record with no semantic detail is not treated as proof.
    """
    if record is None:
        return False
    flag_keys = [k for k in record if k not in _NAME_KEYS]
    if not flag_keys:
        return False
    return not all(record.get(key) is False for key in flag_keys)


def _result(
    requirement: VerificationRequirement,
    status: CheckStatus,
    *,
    expected: Any,
    actual: Any,
    evidence_refs: list[str],
    note: str,
    source: str,
    extra: dict[str, Any] | None = None,
) -> VerificationCheckResult:
    details: dict[str, Any] = {"note": note, "source": source}
    if extra:
        details.update(extra)
    return VerificationCheckResult(
        requirement_id=requirement.id,
        status=status,
        expected=expected,
        actual=actual,
        tolerance=None,
        evidence_refs=list(evidence_refs),
        details=details,
        is_mandatory=requirement.is_mandatory,
    )


def execute_check(
    check_id: str,
    requirement: VerificationRequirement,
    *,
    recorded_events: list[dict[str, Any]] | None = None,
    required_event: str | None = None,
    forbidden_event: str | None = None,
    expected_event_order: list[str] | None = None,
    event_count: dict[str, int] | None = None,
    evidence_complete: bool | None = None,
    source: str = "event_check",
) -> VerificationCheckResult:
    """Execute an event verification check.

    Args:
        check_id: Identifier for this check (provenance only).
        requirement: The ``VerificationRequirement`` describing the contract.
        recorded_events: Event dicts recorded during the run.
        required_event: Event that must have occurred.
        forbidden_event: Event that must not have occurred.
        expected_event_order: Required relative order of first occurrences.
        event_count: Minimum required count per event name.
        evidence_complete: ``True`` when the caller guarantees
            *recorded_events* is the complete event stream.  Only then can a
            missing event be reported as a violation.
        source: Provenance label recorded in ``details``.

    Returns:
        A ``VerificationCheckResult`` with status ``PASS``, ``FAIL`` or
        ``UNKNOWN``.
    """
    expected = requirement.expected_value
    evidence_complete = bool(evidence_complete)

    has_constraint = any(
        value is not None
        for value in (
            required_event,
            forbidden_event,
            expected_event_order,
            event_count if event_count else None,
        )
    )
    if not has_constraint:
        return _result(
            requirement,
            CheckStatus.UNKNOWN,
            expected=expected,
            actual=None,
            evidence_refs=[],
            note=(
                "No event constraint (required/forbidden event, order or "
                "count) is defined for this requirement; nothing to evaluate"
            ),
            source=source,
        )

    if recorded_events is None:
        return _result(
            requirement,
            CheckStatus.UNKNOWN,
            expected=expected,
            actual=None,
            evidence_refs=[],
            note="No recorded events supplied; event evidence is unavailable",
            source=source,
        )

    # Remove re-delivered duplicates before any constraint is evaluated.
    recorded_events = _deduplicate(recorded_events)

    satisfied: list[str] = []

    # ---- required_event -------------------------------------------------
    if required_event is not None:
        record = _find_record(recorded_events, required_event)
        if _occurred(record):
            satisfied.append(f"required_event:{required_event}")
        elif not evidence_complete:
            return _result(
                requirement,
                CheckStatus.UNKNOWN,
                expected=expected,
                actual=None,
                evidence_refs=_collect_refs(recorded_events, {required_event}, limit=20),
                note=(
                    f"Required event {required_event!r} was not found in the "
                    "recorded events, but evidence coverage is not asserted "
                    "complete; this is inconclusive, not a violation"
                ),
                source=source,
            )
        else:
            return _result(
                requirement,
                CheckStatus.FAIL,
                expected=expected,
                actual=None,
                evidence_refs=_collect_refs(recorded_events, {required_event}, limit=20),
                note=(
                    f"Required event {required_event!r} was not recorded although "
                    "the evidence stream is asserted complete"
                ),
                source=source,
            )

    # ---- forbidden_event ------------------------------------------------
    if forbidden_event is not None:
        record = _find_record(recorded_events, forbidden_event)
        if _occurred(record):
            return _result(
                requirement,
                CheckStatus.FAIL,
                expected=expected,
                actual=f"forbidden event {forbidden_event!r} was recorded",
                evidence_refs=_collect_refs(recorded_events, {forbidden_event}, limit=20),
                note=(
                    f"Forbidden event {forbidden_event!r} was recorded but the "
                    "requirement states it must not occur"
                ),
                source=source,
            )
        satisfied.append(f"forbidden_event:{forbidden_event}:absent")

    # ---- expected_event_order -------------------------------------------
    if expected_event_order is not None:
        found_order: list[str] = []
        for record in recorded_events:
            if not isinstance(record, dict):
                continue
            name = _event_name(record)
            if name in expected_event_order and name not in found_order:
                found_order.append(name)

        missing = [name for name in expected_event_order if name not in found_order]
        if missing:
            if not evidence_complete:
                return _result(
                    requirement,
                    CheckStatus.UNKNOWN,
                    expected=expected,
                    actual=found_order,
                    evidence_refs=_collect_refs(recorded_events, set(found_order), limit=20),
                    note=(
                        "Events required for the ordering constraint are missing "
                        f"({missing}) and evidence coverage is not asserted complete"
                    ),
                    source=source,
                )
            return _result(
                requirement,
                CheckStatus.FAIL,
                expected=expected,
                actual=found_order,
                evidence_refs=_collect_refs(recorded_events, set(found_order), limit=20),
                note=f"Events required for the ordering constraint are missing: {missing}",
                source=source,
            )

        observed_order = [name for name in found_order]
        if observed_order != list(expected_event_order):
            return _result(
                requirement,
                CheckStatus.FAIL,
                expected=expected,
                actual=observed_order,
                evidence_refs=_collect_refs(recorded_events, set(observed_order), limit=20),
                note=(
                    f"Event order mismatch: expected {list(expected_event_order)}, "
                    f"observed {observed_order}"
                ),
                source=source,
                extra={"expected_event_order": list(expected_event_order)},
            )
        satisfied.append("event_order")

    # ---- event_count ----------------------------------------------------
    if event_count:
        actual_counts: dict[str, int] = {}
        for record in recorded_events:
            if not isinstance(record, dict):
                continue
            name = _event_name(record)
            if name is not None:
                actual_counts[name] = actual_counts.get(name, 0) + 1

        for name, required_count in event_count.items():
            actual_count = actual_counts.get(name, 0)
            if actual_count < required_count:
                if not evidence_complete:
                    return _result(
                        requirement,
                        CheckStatus.UNKNOWN,
                        expected=expected,
                        actual=actual_counts,
                        evidence_refs=_collect_refs(recorded_events, {name}, limit=20),
                        note=(
                            f"Observed {actual_count} occurrence(s) of {name!r}, "
                            f"fewer than the required {required_count}, but "
                            "evidence coverage is not asserted complete"
                        ),
                        source=source,
                    )
                return _result(
                    requirement,
                    CheckStatus.FAIL,
                    expected=expected,
                    actual=actual_counts,
                    evidence_refs=_collect_refs(recorded_events, {name}, limit=20),
                    note=(
                        f"Observed {actual_count} occurrence(s) of {name!r}, "
                        f"fewer than the required {required_count}"
                    ),
                    source=source,
                )
            satisfied.append(f"event_count:{name}>={required_count}")

    # ---- aggregation ----------------------------------------------------
    if not satisfied:
        return _result(
            requirement,
            CheckStatus.UNKNOWN,
            expected=expected,
            actual=None,
            evidence_refs=[],
            note="No event constraint was actually evaluated against evidence",
            source=source,
        )

    names: set[str] = set()
    for item in satisfied:
        _, _, raw = item.partition(":")
        names.add(raw.split(":", 1)[0])
    if required_event:
        names.add(required_event)
    if forbidden_event:
        names.add(forbidden_event)

    return _result(
        requirement,
        CheckStatus.PASS,
        expected=expected,
        actual="event constraints satisfied",
        evidence_refs=_collect_refs(recorded_events, names, limit=20) or _fallback_refs(recorded_events),
        note="All defined event constraints were satisfied by recorded events",
        source=source,
        extra={"satisfied_constraints": satisfied},
    )


def _fallback_refs(records: list[dict[str, Any]] | None) -> list[str]:
    """Return real event identifiers present in the evidence stream."""
    refs: list[str] = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        ref = _event_ref(record)
        if ref is not None and ref not in refs:
            refs.append(ref)
            if len(refs) >= 20:
                break
    return refs


__all__ = ["execute_check"]
