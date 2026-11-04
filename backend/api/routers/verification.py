"""Verification workflow HTTP API (Person 3).

The route is a thin adapter: it validates the request, invokes the real
``VerificationAgentController`` (which runs the authoritative LangGraph
workflow), and returns the serialised output.  No verification logic is
duplicated here.

The deterministic verdict never depends on a model.  When Meta Model API
credentials are configured the controller uses the real provider; otherwise it
runs with no provider and the diagnosis is reported as not requested or
unavailable.  Tests inject an offline investigator through
``app.state.verification_model_client``, so no test can reach the network.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from backend.ai.service import AIService, get_ai_service
from backend.core.config import settings
from backend.studio.session import store_path
from backend.studio.store import TrajectoryReader
from backend.verification.agent.agent_controller import VerificationAgentController
from backend.verification.exceptions import InputValidationError, VerificationError
from backend.verification.input.input_adapter import adapt_input
from backend.verification.lifecycle import LifecycleError, VerificationLifecycle
from backend.verification.storage.verification_store import InMemoryVerificationStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/verification", tags=["verification"])

_UNSET = object()


def _error(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


def _store(request: Request) -> InMemoryVerificationStore:
    store = getattr(request.app.state, "verification_store", None)
    if store is None:
        store = InMemoryVerificationStore()
        request.app.state.verification_store = store
    return store


def _model_client(request: Request) -> Any | None:
    override = getattr(request.app.state, "verification_model_client", _UNSET)
    if override is not _UNSET:
        return override
    if not settings.meta_ai_api_key:
        return None
    try:
        from backend.verification.llm.meta_ai import get_meta_ai_provider

        return get_meta_ai_provider()
    except Exception:  # noqa: BLE001 - provider configuration is optional
        logger.warning("Meta AI provider is configured but unavailable")
        return None


def _controller(request: Request) -> VerificationAgentController:
    return VerificationAgentController(
        model_client=_model_client(request),
        storage=_store(request),
    )


@router.get("/status")
def verification_status() -> dict[str, Any]:
    """Report availability without exposing credentials or model calls."""
    try:
        hosted_ai: dict[str, Any] | None = get_ai_service().status()
    except Exception:  # noqa: BLE001 - status must never fail because AI is misconfigured
        hosted_ai = None
    return {
        "hosted_ai": hosted_ai,
        "status": "ready",
        "deterministic_verification": True,
        "meta_ai_provider": "configured" if settings.meta_ai_api_key else "unavailable",
        "provider": "grok" if settings.meta_ai_api_key else "unavailable",
        "note": (
            "Deterministic verification works with the Grok/xAI provider "
            "unavailable. A missing provider is reported, never simulated."
        ),
    }


@router.post("/verify")
def verify(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Run the authoritative verification workflow for one input payload."""
    try:
        input_data = adapt_input(payload)
    except InputValidationError as exc:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_verification_input",
            "The verification input is invalid.",
            {"reason": exc.message},
        ) from exc
    except Exception as exc:
        logger.warning("Verification input adaptation failed: %s", type(exc).__name__)
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_verification_input",
            "The verification input could not be adapted.",
        ) from exc

    try:
        output = _controller(request).run_verification_output(input_data)
    except InputValidationError as exc:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_verification_input",
            "The verification input is invalid.",
            {"reason": exc.message},
        ) from exc
    except VerificationError as exc:
        logger.exception("Verification workflow failed")
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "verification_failed",
            "The verification workflow failed.",
            {"reason": exc.error_code},
        ) from exc
    except Exception as exc:
        logger.exception("Verification workflow failed unexpectedly")
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "verification_failed",
            "The verification workflow failed.",
        ) from exc

    if not isinstance(output, dict):
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "verification_failed",
            "The verification workflow produced no serialisable result.",
        )
    return output


# =====================================================================================================
# Phase 3: intent -> requirements -> confirmation -> deterministic verification -> incident handoff
# =====================================================================================================
_ID_PATTERN = r"^[A-Za-z0-9_.:\-]{1,128}$"
RunId = Annotated[str, Path(pattern=_ID_PATTERN, description="Studio run id")]
ObjId = Annotated[str, Path(pattern=_ID_PATTERN)]
Operator = Literal["==", "!=", ">=", "<=", ">", "<"]


class IntentContext(BaseModel):
    """Optional structured context. ``environment_version`` scopes the resulting requirements."""

    model_config = ConfigDict(extra="forbid")
    environment_version: str | None = Field(default=None, max_length=100)
    environment: str | None = Field(default=None, max_length=100)
    agent: str | None = Field(default=None, max_length=100)


class IntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=1, max_length=4000)
    context: IntentContext | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class Overrides(BaseModel):
    """Values the developer states explicitly while confirming (never inferred)."""

    model_config = ConfigDict(extra="forbid")
    expected_value: float | int | str | bool | None = None
    comparison_operator: Operator | None = None
    tolerance: float | None = Field(default=None, ge=0)
    metric_name: str | None = Field(default=None, max_length=120)
    config_key: str | None = Field(default=None, max_length=160)
    max_steps: int | None = Field(default=None, gt=0)
    required_event: str | None = Field(default=None, max_length=120)
    forbidden_event: str | None = Field(default=None, max_length=120)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overrides: Overrides | None = None


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = Field(default=None, max_length=500)


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_ids: list[str] | None = Field(default=None, min_length=1, max_length=50)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


def _lifecycle(request: Request) -> VerificationLifecycle:
    state = request.app.state
    database = getattr(state, "database", None)
    services = getattr(state, "services", None)
    if database is None or services is None:
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "service_unavailable", "The application is not ready.")
    ai: AIService | None = getattr(state, "ai_service", None)
    if ai is None:
        ai = get_ai_service()
    return VerificationLifecycle(
        database=database,
        reader=TrajectoryReader(store_path()),
        provenance=services.provenance,
        ai=ai,
        incident_sink=getattr(state, "verification_incident_sink", None),
    )


def _run(fn: Any) -> Any:
    """Invoke a lifecycle call, translating typed errors; internals are never leaked."""
    try:
        return fn()
    except LifecycleError as exc:
        raise _error(exc.http_status, exc.code, exc.message, exc.details) from exc
    except Exception as exc:
        logger.exception("Verification lifecycle failed unexpectedly (%s)", type(exc).__name__)
        raise _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "verification_failed", "The verification workflow failed.") from exc


@router.post("/runs/{run_id}/intents", status_code=status.HTTP_201_CREATED)
def submit_intent(run_id: RunId, body: IntentRequest, response: Response, request: Request) -> dict[str, Any]:
    """Interpret natural-language expectations for a real Studio run and propose requirements."""
    ctx = body.context.model_dump(exclude_none=True) if body.context else {}
    view = _run(lambda: _lifecycle(request).submit_intent(run_id, body.statement, ctx, body.idempotency_key))
    if view.get("replayed"):
        response.status_code = status.HTTP_200_OK
    return view


@router.get("/runs/{run_id}/intents")
def list_intents(run_id: RunId, request: Request) -> dict[str, Any]:
    items = _run(lambda: _lifecycle(request).list_intents(run_id))
    return {"run_id": run_id, "count": len(items), "intents": items}


@router.get("/intents/{intent_id}")
def get_intent(intent_id: ObjId, request: Request) -> dict[str, Any]:
    return _run(lambda: _lifecycle(request).get_intent(intent_id))


@router.get("/runs/{run_id}/requirements")
def list_requirements(run_id: RunId, request: Request) -> dict[str, Any]:
    items = _run(lambda: _lifecycle(request).list_requirements(run_id))
    return {"run_id": run_id, "count": len(items), "requirements": items}


@router.get("/requirements/{requirement_id}")
def get_requirement(requirement_id: ObjId, request: Request) -> dict[str, Any]:
    return _run(lambda: _lifecycle(request).get_requirement(requirement_id))


@router.post("/requirements/{requirement_id}/confirm")
def confirm_requirement(requirement_id: ObjId, request: Request, body: ConfirmRequest | None = None) -> dict[str, Any]:
    overrides = body.overrides.model_dump(exclude_unset=True) if body and body.overrides else None
    return _run(lambda: _lifecycle(request).confirm_requirement(requirement_id, overrides))


@router.post("/requirements/{requirement_id}/reject")
def reject_requirement(requirement_id: ObjId, request: Request, body: RejectRequest | None = None) -> dict[str, Any]:
    return _run(lambda: _lifecycle(request).reject_requirement(requirement_id, body.reason if body else None))


@router.post("/runs/{run_id}/verifications", status_code=status.HTTP_201_CREATED)
def execute_verification(
    run_id: RunId, response: Response, request: Request, body: ExecuteRequest | None = None
) -> dict[str, Any]:
    """Run the deterministic engine over confirmed requirements and persist the result."""
    ids = body.requirement_ids if body else None
    key = body.idempotency_key if body else None
    view = _run(lambda: _lifecycle(request).execute(run_id, ids, key))
    if view.get("replayed"):
        response.status_code = status.HTTP_200_OK
    return view


@router.get("/runs/{run_id}/verifications")
def list_verifications(run_id: RunId, request: Request) -> dict[str, Any]:
    items = _run(lambda: _lifecycle(request).list_verifications(run_id))
    return {"run_id": run_id, "count": len(items), "verifications": items}


@router.get("/verifications/{verification_id}")
def get_verification(verification_id: ObjId, request: Request) -> dict[str, Any]:
    return _run(lambda: _lifecycle(request).get_verification(verification_id))


@router.get("/verifications/{verification_id}/results")
def get_verification_results(verification_id: ObjId, request: Request) -> dict[str, Any]:
    results = _run(lambda: _lifecycle(request).get_results(verification_id))
    return {"verification_id": verification_id, "count": len(results), "results": results}


@router.post("/verifications/{verification_id}/incident/retry")
def retry_incident_handoff(verification_id: ObjId, request: Request) -> dict[str, Any]:
    """Re-attempt the (idempotent) incident handoff for a verification whose first attempt failed."""
    return _run(lambda: _lifecycle(request).retry_handoff(verification_id))


__all__ = ["router"]
