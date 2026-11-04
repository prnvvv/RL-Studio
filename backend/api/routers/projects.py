"""Project management HTTP API.

A thin adapter over ``backend.projects.service.ProjectService``. Intent processing, confirmation and
verification are the Phase 3 lifecycle; this router adds no verification logic.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from backend.ai.service import AIService, get_ai_service
from backend.projects import documents as docs
from backend.projects.service import ProjectService
from backend.studio.session import store_path
from backend.studio.store import TrajectoryReader
from backend.verification.lifecycle import LifecycleError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

ProjectId = Annotated[str, Path(pattern=r"^prj_[0-9a-f]{16}$")]
ObjId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_.:\-]{1,128}$")]


class IntentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str | None = Field(default=None, max_length=20000)
    document_ids: list[str] = Field(default_factory=list, max_length=10)


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    agent: dict[str, Any] | None = None
    environment: dict[str, Any] | None = None
    intent: IntentInput | None = None


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    agent: dict[str, Any] | None = None
    environment: dict[str, Any] | None = None


class ProjectDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_name: str = Field(min_length=1, max_length=200)


class ProjectIntentRequest(IntentInput):
    run_id: str | None = Field(default=None, max_length=128)
    supersedes: str | None = Field(default=None, max_length=128)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=100)


class ConfirmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overrides: dict[str, Any] | None = None


class RejectBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)


class VerifyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str = Field(max_length=128)
    requirement_ids: list[str] | None = Field(default=None, min_length=1, max_length=50)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


def _error(status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message, "details": details or {}}})


def _service(request: Request) -> ProjectService:
    state = request.app.state
    database, services = getattr(state, "database", None), getattr(state, "services", None)
    if database is None or services is None:
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "service_unavailable", "The application is not ready.")
    ai: AIService | None = getattr(state, "ai_service", None)
    if ai is None:
        try:
            ai = get_ai_service()
        except Exception:  # noqa: BLE001 - interpretation reports the provider as unavailable; CRUD still works
            ai = None
    return ProjectService(
        database=database, reader=TrajectoryReader(store_path()), provenance=services.provenance, ai=ai,
        incident_sink=getattr(state, "verification_incident_sink", None),
    )


def _call(fn: Any) -> Any:
    try:
        return fn()
    except LifecycleError as exc:
        raise _error(exc.http_status, exc.code, exc.message, exc.details) from exc
    except Exception as exc:
        logger.exception("Project operation failed unexpectedly (%s)", type(exc).__name__)
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "project_operation_failed", "The operation failed.") from exc


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, request: Request) -> dict[str, Any]:
    svc = _service(request)
    project = _call(lambda: svc.create_project(body.name, body.description, body.agent, body.environment))
    if body.intent and (body.intent.statement or body.intent.document_ids):
        # The project exists regardless of what happens to the intent: a provider failure is reported, not fatal.
        try:
            project["intent"] = svc.submit_intent(project["project_id"], body.intent.statement, body.intent.document_ids)
        except LifecycleError as exc:
            project["intent"] = {"error": {"code": exc.code, "message": exc.message, "details": exc.details}}
        except Exception as exc:  # noqa: BLE001
            logger.warning("initial intent failed for %s: %s", project["project_id"], type(exc).__name__)
            project["intent"] = {"error": {"code": "intent_failed", "message": "The expectation could not be processed.", "details": {}}}
    return project


@router.get("")
def list_projects(request: Request) -> dict[str, Any]:
    items = _call(lambda: _service(request).list_projects())
    return {"count": len(items), "projects": items}


@router.get("/legacy-runs")
def legacy_runs(request: Request) -> dict[str, Any]:
    items = _call(lambda: _service(request).legacy_runs())
    return {"count": len(items), "runs": items}


@router.get("/{project_id}")
def get_project(project_id: ProjectId, request: Request) -> dict[str, Any]:
    return _call(lambda: _service(request).get_project(project_id))


@router.patch("/{project_id}")
def update_project(project_id: ProjectId, body: ProjectUpdate, request: Request) -> dict[str, Any]:
    return _call(lambda: _service(request).update_project(project_id, body.model_dump(exclude_unset=True)))


@router.delete("/{project_id}")
def delete_project(project_id: ProjectId, body: ProjectDelete, request: Request) -> dict[str, Any]:
    return _call(lambda: _service(request).delete_project(project_id, body.confirm_name))


@router.post("/{project_id}/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    project_id: ProjectId, request: Request, response: Response,
    filename: str = Query(..., min_length=1, max_length=200),
) -> dict[str, Any]:
    """Upload an intent document as the raw request body (``?filename=requirements.md``)."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > docs.MAX_DOCUMENT_BYTES:
        raise _error(status.HTTP_413_CONTENT_TOO_LARGE, "payload_too_large", "The file is too large", {"max_bytes": docs.MAX_DOCUMENT_BYTES})
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > docs.MAX_DOCUMENT_BYTES:
            raise _error(status.HTTP_413_CONTENT_TOO_LARGE, "payload_too_large", "The file is too large", {"max_bytes": docs.MAX_DOCUMENT_BYTES})
    svc = _service(request)
    record, duplicate = await run_in_threadpool(
        lambda: _call(lambda: svc.add_document(project_id, filename, request.headers.get("content-type"), bytes(data))))
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return {"document": record, "duplicate": duplicate}


@router.get("/{project_id}/documents")
def list_documents(project_id: ProjectId, request: Request) -> dict[str, Any]:
    items = _call(lambda: _service(request).list_documents(project_id))
    return {"count": len(items), "documents": items}


@router.post("/{project_id}/intents", status_code=status.HTTP_201_CREATED)
def submit_intent(project_id: ProjectId, body: ProjectIntentRequest, request: Request) -> dict[str, Any]:
    """Interpret expectations (text and/or documents) into project requirements, before, during or after training."""
    return _call(lambda: _service(request).submit_intent(
        project_id, body.statement, body.document_ids, body.run_id, body.idempotency_key, body.supersedes))


@router.get("/{project_id}/intents")
def list_intents(project_id: ProjectId, request: Request) -> dict[str, Any]:
    items = _call(lambda: _service(request).list_intents(project_id))
    return {"count": len(items), "intents": items}


@router.get("/{project_id}/requirements")
def list_requirements(project_id: ProjectId, request: Request) -> dict[str, Any]:
    items = _call(lambda: _service(request).list_requirements(project_id))
    return {"count": len(items), "requirements": items}


@router.post("/{project_id}/requirements/{requirement_id}/confirm")
def confirm_requirement(project_id: ProjectId, requirement_id: ObjId, request: Request, body: ConfirmBody | None = None) -> dict[str, Any]:
    overrides = body.overrides if body else None
    return _call(lambda: _service(request).confirm_requirement(project_id, requirement_id, overrides))


@router.post("/{project_id}/requirements/{requirement_id}/reject")
def reject_requirement(project_id: ProjectId, requirement_id: ObjId, request: Request, body: RejectBody | None = None) -> dict[str, Any]:
    return _call(lambda: _service(request).reject_requirement(project_id, requirement_id, body.reason if body else None))


@router.get("/{project_id}/runs")
def list_runs(project_id: ProjectId, request: Request) -> dict[str, Any]:
    items = _call(lambda: _service(request).list_runs(project_id))
    return {"count": len(items), "runs": items}


@router.post("/{project_id}/runs/{run_id}/adopt")
def adopt_run(project_id: ProjectId, run_id: ObjId, request: Request) -> dict[str, Any]:
    """Explicitly associate a legacy run (one created before projects existed) with this project."""
    return _call(lambda: _service(request).adopt_run(project_id, run_id))


@router.post("/{project_id}/verifications")
def verify(project_id: ProjectId, body: VerifyBody, request: Request, response: Response) -> dict[str, Any]:
    """Verify confirmed project requirements against one of this project's runs (active or finished)."""
    result = _call(lambda: _service(request).verify(project_id, body.run_id, body.requirement_ids, body.idempotency_key))
    if result["state"] == "waiting_for_evidence":
        response.status_code = status.HTTP_202_ACCEPTED
    else:
        response.status_code = status.HTTP_201_CREATED
    return result


@router.get("/{project_id}/verifications")
def list_verifications(project_id: ProjectId, request: Request, run_id: str | None = Query(default=None, max_length=128)) -> dict[str, Any]:
    items = _call(lambda: _service(request).list_verifications(project_id, run_id))
    return {"count": len(items), "verifications": items}


@router.get("/{project_id}/verifications/{verification_id}")
def get_verification(project_id: ProjectId, verification_id: ObjId, request: Request) -> dict[str, Any]:
    return _call(lambda: _service(request).run_verification_detail(project_id, verification_id))


__all__ = ["router"]
