"""Incident diagnosis, root-cause investigation and advisory recovery recommendations.

Every route is project-scoped by ``enforce_project_scope`` (the path ``incident_id`` resolves to its run and project).
Results are advisory model output grounded in persisted evidence (``backend/diagnosis``): they never decide a
verification verdict and never execute a recovery. Executing a recovery stays with the existing
``/api/v1/incidents/{incident_id}/recovery-assessments`` and ``/recoveries`` endpoints and their authorization rules.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from backend.ai.errors import AIError
from backend.ai.registry import Task
from backend.ai.service import AIService, get_ai_service
from backend.diagnosis.service import DiagnosisService, InvestigationNotFound
from backend.studio.session import store_path
from backend.studio.store import TrajectoryReader
from backend.verification.lifecycle import VerificationLifecycle

from ..dependencies import Services, get_services

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["diagnosis"])

_REASONING_TASKS = (Task.ROOT_CAUSE, Task.INVESTIGATION, Task.RECOVERY_PLANNING)


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: re-run even if an analysis of the identical evidence already exists (spends credits)
    force: bool = False


def _service(request: Request, services: Services) -> DiagnosisService:
    database = request.app.state.database
    ai: AIService = getattr(request.app.state, "ai_service", None) or get_ai_service()
    lifecycle = VerificationLifecycle(
        database=database, reader=TrajectoryReader(store_path()), provenance=services.provenance, ai=ai,
    )

    def catalogue(run_id: str) -> dict[str, Any]:
        prepared = lifecycle.prepare_evidence(run_id)
        return {"catalogue": prepared.facts.describe(),
                "missing": [str(m) for m in (getattr(prepared.evidence, "missing_evidence", None) or [])]}

    return DiagnosisService(database, services.provenance, ai, catalogue_provider=catalogue)


def _ai_error(exc: AIError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status,
                        content={"error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable}})


def _respond(fn: Any, response: Response) -> Any:
    try:
        record = fn()
    except AIError as exc:
        return _ai_error(exc)
    response.status_code = status.HTTP_200_OK if record.get("reused") else status.HTTP_201_CREATED
    return record


@router.get("/diagnosis/status")
def diagnosis_status() -> dict[str, Any]:
    """Whether the reasoning tasks are configured (no credentials, no model call)."""
    tasks = get_ai_service().status()["tasks"]
    return {"tasks": {t.value: tasks[t.value] for t in _REASONING_TASKS},
            "note": "configured is not verified; run the connectivity check to verify model access"}


@router.post("/incidents/{incident_id}/investigations", summary="Investigate an incident's root cause (advisory)")
def investigate(incident_id: str, request: Request, response: Response,
                services: Annotated[Services, Depends(get_services)],
                body: InvestigationRequest | None = None) -> Any:
    svc = _service(request, services)
    return _respond(lambda: svc.investigate(incident_id, force=bool(body and body.force)), response)


@router.post("/incidents/{incident_id}/recovery-recommendations", summary="Recommend recovery options (advisory, never executed)")
def recommend(incident_id: str, request: Request, response: Response,
              services: Annotated[Services, Depends(get_services)],
              body: InvestigationRequest | None = None) -> Any:
    svc = _service(request, services)
    return _respond(lambda: svc.recommend_recovery(incident_id, force=bool(body and body.force)), response)


@router.get("/incidents/{incident_id}/investigations", summary="List an incident's advisory investigations")
def list_investigations(incident_id: str, request: Request,
                        services: Annotated[Services, Depends(get_services)]) -> dict[str, Any]:
    items = _service(request, services).list(incident_id)
    return {"incident_id": incident_id, "count": len(items), "investigations": items}


@router.get("/incidents/{incident_id}/investigations/{investigation_id}", summary="Get one advisory investigation")
def get_investigation(incident_id: str, investigation_id: str, request: Request,
                      services: Annotated[Services, Depends(get_services)]) -> Any:
    try:
        return _service(request, services).get(incident_id, investigation_id)
    except InvestigationNotFound:
        return JSONResponse(status_code=404, content={"error": {"code": "investigation_not_found",
                                                                  "message": "The investigation was not found for this incident."}})
