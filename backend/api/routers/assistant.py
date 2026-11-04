"""Conversational assistant API.

``POST /api/v1/assistant/chat`` answers with or without an incident: the general assistant needs no incident, run or
verification record. The project comes from the validated ``X-Project-ID`` scope (never from the body); a run or incident
named in the body is checked against that scope exactly like a path parameter would be.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.ai.errors import AIError
from backend.ai.service import AIService, get_ai_service
from backend.assistant.service import MAX_HISTORY, MAX_MESSAGE_CHARS, AssistantError, AssistantService
from backend.projects.scope import Denied, authorize, scope_of
from backend.projects.service import ProjectService
from backend.studio.session import store_path
from backend.studio.store import TrajectoryReader
from backend.verification.lifecycle import VerificationLifecycle

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY * 2)
    run_id: Annotated[str | None, Field(max_length=128)] = None
    #: when set the investigator answers about this one incident; when absent the general assistant answers
    incident_id: Annotated[str | None, Field(max_length=128)] = None


def _error(status: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, **extra}})


def _service(request: Request, ai: AIService) -> AssistantService:
    state = request.app.state
    database, services = state.database, state.services
    projects = ProjectService(database=database, reader=TrajectoryReader(store_path()), provenance=services.provenance, ai=ai,
                              incident_sink=getattr(state, "verification_incident_sink", None))
    lifecycle = VerificationLifecycle(database=database, reader=TrajectoryReader(store_path()), provenance=services.provenance, ai=ai)

    def catalogue(run_id: str) -> dict[str, Any]:
        prepared = lifecycle.prepare_evidence(run_id)
        return {"catalogue": prepared.facts.describe(),
                "missing": [str(m) for m in (getattr(prepared.evidence, "missing_evidence", None) or [])]}

    return AssistantService(database, services.provenance, ai, requirements_provider=projects.list_requirements,
                            catalogue_provider=catalogue)


@router.get("/status")
def assistant_status() -> dict[str, Any]:
    """Whether the assistant's models are configured (no credentials, no model call)."""
    tasks = get_ai_service().status()["tasks"]
    return {"general": tasks["general_assistance"], "incident": tasks["investigation_assistance"],
            "note": "configured is not verified; run the connectivity check to verify model access"}


@router.post("/chat")
def chat(body: ChatRequest, request: Request) -> Any:
    scope = scope_of(request)
    params = {k: v for k, v in (("run_id", body.run_id), ("incident_id", body.incident_id)) if v}
    try:
        authorize(request, request.app.state.database, params)
    except Denied:
        return _error(404, "not_found", "The requested record was not found.")
    try:
        ai = getattr(request.app.state, "ai_service", None) or get_ai_service()
        return _service(request, ai).chat(
            message=body.message, history=[t.model_dump() for t in body.history], project_id=scope,
            run_id=body.run_id, incident_id=body.incident_id)
    except AssistantError as exc:
        return _error(exc.http_status, exc.code, exc.message)
    except AIError as exc:
        return _error(exc.http_status, exc.code, exc.message, retryable=exc.retryable)
