"""Person 3 -> Person 4 incident handoff.

Verification owns **detection**; it does not own persistence.  This package
implements the Person 3 side of the agreed handoff:

1. ``build_incident_draft`` turns a real, serialised verification output into an
   ``IncidentDraft``.  It only ever derives values that are present in the
   output: a run identifier, failed mandatory requirement IDs, real evidence
   references and provenance identifiers.  When the verdict is not a failure it
   returns ``None``; it never manufactures an incident.
2. ``ProvenanceIncidentSink`` translates the draft into Person 4's public
   ``IncidentRegistration`` contract and calls ``ProvenanceService``.  Person 4
   remains authoritative for persistence, audit and validation.  The record is
   read back and checked before success is reported.

No database module is modified here, and no success is reported without a
stored record.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from backend.verification.exceptions import VerificationError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from backend.provenance.models import IncidentRegistration
    from backend.provenance.service import ProvenanceService

#: Person 4 incident lifecycle status for a freshly detected record.
P4_INCIDENT_STATUS = "detected"

#: Person 3 detection status recorded in incident details.  Detection status,
#: diagnosis status and resolution status are separate dimensions.
DETECTION_STATUS_CONFIRMED = "confirmed_violation"

_DETECTION_METHOD = "deterministic_contract_check"
_DETECTOR_VERSION = "1.0"

#: Verification statuses that represent an incident worth recording.
_INCIDENT_STATUSES = frozenset({"fail", "error"})


class IncidentContractError(VerificationError):
    """Raised when verification evidence cannot be handed to Person 4 safely."""

    error_code: str = "VERG-050"


@dataclass(frozen=True)
class IncidentDraft:
    """The minimum, evidence-backed incident data Person 3 can hand over."""

    incident_id: str
    run_id: str
    status: str
    detection_status: str
    severity: str
    detection_method: str
    summary: str
    requirement_id: str | None = None
    verification_id: str | None = None
    environment_id: str | None = None
    environment_version: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


class IncidentSink(Protocol):
    """Persistence boundary for an ``IncidentDraft``."""

    def record(self, draft: IncidentDraft) -> dict[str, Any]:
        """Persist *draft* and return the stored incident record."""
        ...


def _failed_requirements(output: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    requirements = output.get("requirements")
    if not isinstance(requirements, Mapping):
        return []
    failed: list[tuple[str, dict[str, Any]]] = []
    for requirement_id, result in requirements.items():
        if not isinstance(requirement_id, str) or not isinstance(result, Mapping):
            continue
        status = result.get("status")
        is_mandatory = result.get("is_mandatory", True)
        if status in _INCIDENT_STATUSES and is_mandatory is not False:
            failed.append((requirement_id, dict(result)))
    return failed


def _evidence_ids(failed: list[tuple[str, dict[str, Any]]]) -> list[str]:
    seen: list[str] = []
    for _, result in failed:
        refs = result.get("evidence_refs")
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if isinstance(ref, str) and ref and ref not in seen:
                seen.append(ref)
    return seen


def build_incident_draft(
    output: Mapping[str, Any],
    *,
    run_id: str | None = None,
    incident_id: str | None = None,
) -> IncidentDraft | None:
    """Build an ``IncidentDraft`` from real verification output, or ``None``.

    Raises:
        IncidentContractError: When the verdict is a failure but no run
            identifier is available.  An unattributed incident is not stored:
            "impact unknown" must never be presented as "registered".
    """
    if not isinstance(output, Mapping):
        raise IncidentContractError(
            "Verification output must be a mapping.",
            details={"received": type(output).__name__},
        )

    overall = output.get("overall_status")
    failed = _failed_requirements(output)
    if overall not in _INCIDENT_STATUSES or not failed:
        return None

    resolved_run_id = run_id or output.get("run_identifier")
    if not isinstance(resolved_run_id, str) or not resolved_run_id.strip():
        raise IncidentContractError(
            "A run identifier is required to register an incident; none was "
            "supplied by the verification output.",
            details={"verification_id": output.get("verification_id")},
        )

    environment_id = output.get("environment_identifier")
    environment_version = output.get("environment_version")
    failed_ids = [requirement_id for requirement_id, _ in failed]
    evidence_ids = _evidence_ids(failed)
    verification_id = output.get("verification_id")
    verification_id = verification_id if isinstance(verification_id, str) else None

    details: dict[str, Any] = {
        "detection_status": DETECTION_STATUS_CONFIRMED,
        "detector_version": _DETECTOR_VERSION,
        "contract_status": output.get("contract_status"),
        "failed_requirement_ids": failed_ids,
        "failed_requirement_count": len(failed_ids),
    }
    if verification_id:
        details["verification_id"] = verification_id
    definitions = {
        d.get("id"): d for d in (output.get("requirement_definitions") or []) if isinstance(d, Mapping)
    }
    # Every failed requirement is carried (the registry's single ``requirement_id`` column only holds
    # the first), each with its own expected/actual values and evidence references.
    details["failed_requirements"] = [
        {
            "requirement_id": rid,
            "description": (definitions.get(rid) or {}).get("description"),
            "status": result.get("status"),
            "expected": result.get("expected"),
            "actual": result.get("actual"),
            "evidence_refs": [r for r in (result.get("evidence_refs") or []) if isinstance(r, str)],
            "note": (result.get("details") or {}).get("note") if isinstance(result.get("details"), Mapping) else None,
        }
        for rid, result in failed
    ]
    consistency = output.get("consistency")
    if isinstance(consistency, Mapping):
        details["consistency_status"] = consistency.get("status")
        details["contradiction_count"] = len(consistency.get("contradictions") or [])
    anomalies = output.get("anomalies")
    if isinstance(anomalies, list):
        details["anomaly_count"] = len(anomalies)

    return IncidentDraft(
        incident_id=incident_id or str(uuid.uuid4()),
        run_id=resolved_run_id.strip(),
        status=P4_INCIDENT_STATUS,
        detection_status=DETECTION_STATUS_CONFIRMED,
        detection_method=_DETECTION_METHOD,
        severity="high",
        summary=(
            "Deterministic verification detected "
            f"{len(failed_ids)} contract violation(s): "
            + ", ".join(failed_ids)
        ),
        requirement_id=failed_ids[0] if failed_ids else None,
        verification_id=verification_id,
        environment_id=environment_id if isinstance(environment_id, str) else None,
        environment_version=(
            environment_version if isinstance(environment_version, str) else None
        ),
        evidence_ids=evidence_ids,
        details=details,
    )


def build_registration(draft: IncidentDraft) -> IncidentRegistration:
    """Translate the draft into Person 4's public registration contract."""
    from backend.provenance.models import IncidentRegistration

    return IncidentRegistration(
        incident_id=draft.incident_id,
        run_id=draft.run_id,
        status=draft.status,
        verification_id=draft.verification_id,
        environment_id=draft.environment_id,
        environment_version=draft.environment_version,
        requirement_id=draft.requirement_id,
        severity=draft.severity,
        detection_method=draft.detection_method,
        summary=draft.summary,
        evidence_ids=list(draft.evidence_ids),
        details=dict(draft.details),
    )


class InMemoryIncidentSink:
    """Append-only, in-memory sink for offline tests and local verification."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def record(self, draft: IncidentDraft) -> dict[str, Any]:
        existing = self._records.get(draft.incident_id)
        if existing is not None:
            if existing["run_id"] != draft.run_id:
                raise IncidentContractError(
                    "Incident ID is already recorded for a different run.",
                    details={"incident_id": draft.incident_id},
                )
            return dict(existing)
        record = {
            "incident_id": draft.incident_id,
            "run_id": draft.run_id,
            "verification_id": draft.verification_id,
            "environment_id": draft.environment_id,
            "environment_version": draft.environment_version,
            "requirement_id": draft.requirement_id,
            "status": draft.status,
            "severity": draft.severity,
            "detection_method": draft.detection_method,
            "summary": draft.summary,
            "evidence_ids": list(draft.evidence_ids),
            "details": dict(draft.details),
        }
        self._records[draft.incident_id] = record
        return dict(record)

    def get(self, incident_id: str) -> dict[str, Any] | None:
        record = self._records.get(incident_id)
        return dict(record) if record is not None else None

    def snapshot(self) -> dict[str, Any]:
        return {"incidents": len(self._records)}


class ProvenanceIncidentSink:
    """Person 4-backed sink using the public ``ProvenanceService`` contract.

    Person 4 owns registration, audit and conflict handling.  This adapter
    verifies the read-back record before reporting success.
    """

    def __init__(self, provenance: ProvenanceService) -> None:
        self._provenance = provenance

    def record(self, draft: IncidentDraft) -> dict[str, Any]:
        incident = self._provenance.register_incident(build_registration(draft))
        stored = incident.model_dump(mode="python")
        if stored.get("incident_id") != draft.incident_id:
            raise IncidentContractError(
                "The provenance registry did not return the incident that was "
                "submitted; persistence cannot be confirmed.",
                details={"incident_id": draft.incident_id},
            )
        return stored


__all__ = [
    "DETECTION_STATUS_CONFIRMED",
    "InMemoryIncidentSink",
    "IncidentContractError",
    "IncidentDraft",
    "IncidentSink",
    "P4_INCIDENT_STATUS",
    "ProvenanceIncidentSink",
    "build_incident_draft",
    "build_registration",
]
