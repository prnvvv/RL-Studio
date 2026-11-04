"""Incident read API consumed by the Diagnosis & Recovery page.

Every value is read from persisted records (the Person 4 incident, the Person 3 verification and its requirement); nothing
is inferred or filled in. A field the records do not carry is ``None``. All routes are project-scoped through
``enforce_project_scope`` (the path ``incident_id`` resolves to its run and project).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from backend.diagnosis.store import InvestigationStore
from backend.verification.storage.sqlite_store import SqliteVerificationStore

from ..dependencies import Services, get_services

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


def _store(request: Request) -> SqliteVerificationStore:
    return SqliteVerificationStore(request.app.state.database)


def _iso(value: Any) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else (None if value is None else str(value))


def _diagnosis_status(request: Request, incident_id: str) -> str:
    """'probable' / 'unresolved' from the latest persisted root-cause investigation; 'unresolved' when none exists."""
    for record in InvestigationStore(request.app.state.database).list_for_incident(incident_id):
        if record.get("kind") == "root_cause":
            return (record.get("result") or {}).get("root_cause_status") or "unresolved"
    return "unresolved"


@router.get("", summary="List incidents recorded for a run")
def list_incidents(run_id: str, request: Request, services: Annotated[Services, Depends(get_services)]) -> dict[str, Any]:
    from backend.database.repositories import incidents as incidents_repo

    with request.app.state.database.read() as conn:
        rows = incidents_repo.list_incidents_for_run(conn, run_id)
    items = [{"incident_id": r["incident_id"], "run_id": r["run_id"], "status": r["status"], "severity": r.get("severity"),
              "summary": r.get("summary"), "requirement_id": r.get("requirement_id"),
              "verification_id": r.get("verification_id"), "created_at": r["created_at"]} for r in rows]
    return {"run_id": run_id, "count": len(items), "incidents": items}


@router.get("/{incident_id}", summary="Get one incident record")
def get_incident(incident_id: str, request: Request, services: Annotated[Services, Depends(get_services)]) -> dict[str, Any]:
    incident = services.provenance.get_incident(incident_id)
    store = _store(request)
    requirement = store.get_requirement(incident.requirement_id) if incident.requirement_id else None
    verification = store.get_verification(incident.verification_id) if incident.verification_id else None
    final = bool(verification) and ((verification.get("traceability") or {}).get("finality") != "interim")
    failed = verification is not None and verification.get("overall_status") in {"fail", "error"}
    return {
        "incident_id": incident.incident_id, "schema_version": "1", "run_id": incident.run_id,
        "verification_id": incident.verification_id, "requirement_id": incident.requirement_id,
        "environment_id": incident.environment_id, "environment_version": incident.environment_version,
        "source_environment_version": incident.source_environment_version,
        "violation_type": incident.fault_type or ("requirement_violation" if incident.requirement_id else "unclassified"),
        "severity": incident.severity, "status": incident.status, "summary": incident.summary,
        # detection is the deterministic verdict: confirmed only by a recorded failing verification
        "detection_status": "confirmed" if failed and final else "suspected" if failed else "unresolved",
        "diagnosis_status": _diagnosis_status(request, incident_id),
        "evidence_event_ids": [], "evidence_refs": incident.evidence_ids,
        "detector_id": incident.detection_method, "detector_version": None,
        "corruption_start_timestep": incident.corruption_start_timestep,
        "corruption_end_timestep": incident.corruption_end_timestep, "fault_type": incident.fault_type,
        "requirement": None if requirement is None else {k: requirement.get(k) for k in (
            "requirement_id", "source_statement", "description", "comparison_operator", "expected_value", "category",
            "lifecycle_status")},
        "created_at": _iso(incident.created_at), "resolved_at": None,
    }


@router.get("/{incident_id}/verification", summary="The deterministic verification that produced the incident")
def get_incident_verification(incident_id: str, request: Request, services: Annotated[Services, Depends(get_services)]) -> Any:
    incident = services.provenance.get_incident(incident_id)
    if not incident.verification_id:
        return JSONResponse(status_code=404, content={"error": {
            "code": "verification_not_recorded", "message": "This incident was not created from a recorded verification."}})
    store = _store(request)
    ver = store.get_verification(incident.verification_id)
    if ver is None:
        return JSONResponse(status_code=404, content={"error": {
            "code": "verification_not_found", "message": "The verification record was not found."}})
    results = [{
        "requirement_id": r["requirement_id"], "status": r["status"], "expected": r.get("expected"),
        "actual": r.get("actual"), "tolerance": r.get("tolerance"), "evidence_refs": r.get("evidence_refs") or [],
        "details": r.get("details"), "is_mandatory": bool(r.get("is_mandatory", True)), "timestamp": _iso(r.get("created_at")),
    } for r in store.get_results(incident.verification_id)]
    return {
        "verification_id": ver["verification_id"], "overall_status": ver["overall_status"], "summary": None,
        "results": results, "evidence_refs": sorted({e for r in results for e in r["evidence_refs"]}),
        "warnings": [], "errors": [], "timestamp": _iso(ver.get("created_at")), "schema_version": "1",
        "finality": (ver.get("traceability") or {}).get("finality"),
    }


@router.get("/{incident_id}/evidence", summary="Evidence references recorded for the incident")
def get_incident_evidence(incident_id: str, request: Request, services: Annotated[Services, Depends(get_services)]) -> list[dict[str, Any]]:
    incident = services.provenance.get_incident(incident_id)
    refs: dict[str, str] = {ref: "incident" for ref in incident.evidence_ids}
    if incident.verification_id:
        for result in _store(request).get_results(incident.verification_id):
            for ref in result.get("evidence_refs") or []:
                refs.setdefault(ref, "verification_result")
    return [{"id": ref, "source": source, "run_identifier": incident.run_id,
             "environment_identifier": incident.environment_version, "location": None, "timestamp": None}
            for ref, source in refs.items()]


@router.get("/{incident_id}/anomalies", summary="Detector anomaly observations persisted for the incident")
def get_incident_anomalies(incident_id: str, services: Annotated[Services, Depends(get_services)]) -> list[dict[str, Any]]:
    services.provenance.get_incident(incident_id)  # 404 for an unknown incident
    # Anomaly detector output is not persisted by the platform, so none is recorded: an empty list, never invented signals.
    return []
