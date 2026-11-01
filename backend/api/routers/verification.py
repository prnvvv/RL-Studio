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
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from backend.core.config import settings
from backend.verification.agent.agent_controller import VerificationAgentController
from backend.verification.exceptions import InputValidationError, VerificationError
from backend.verification.input.input_adapter import adapt_input
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
    return {
        "status": "ready",
        "deterministic_verification": True,
        "meta_ai_provider": "configured" if settings.meta_ai_api_key else "unavailable",
        "note": (
            "Deterministic verification works with the Meta AI provider "
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


__all__ = ["router"]
