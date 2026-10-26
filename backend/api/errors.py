from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.database.exceptions import StudioError

from .dependencies import sanitize_correlation_id

logger = logging.getLogger(__name__)


def _correlation_id(request: Request, fallback: str | None = None) -> str:
    return fallback or sanitize_correlation_id(
        request.headers.get("X-Correlation-ID")
    ) or str(uuid.uuid4())


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: object,
    correlation_id: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "correlation_id": correlation_id,
            }
        },
        headers={"X-Correlation-ID": correlation_id},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StudioError)
    async def studio_error_handler(
        request: Request, exc: StudioError
    ) -> JSONResponse:
        return _error_response(
            status_code=exc.http_status,
            code=exc.error_code,
            message=exc.message,
            details=exc.details,
            correlation_id=_correlation_id(request, exc.correlation_id),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "location": list(error.get("loc", [])),
                "message": error.get("msg", "Invalid request value"),
                "type": error.get("type", "validation_error"),
            }
            for error in exc.errors()
        ]
        return _error_response(
            status_code=422,
            code="API-422",
            message="Request validation failed",
            details={"errors": details},
            correlation_id=_correlation_id(request),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        correlation_id = _correlation_id(request)
        logger.exception(
            "Unhandled API error path=%s correlation_id=%s",
            request.url.path,
            correlation_id,
        )
        return _error_response(
            status_code=500,
            code="API-500",
            message="Internal server error",
            details={},
            correlation_id=correlation_id,
        )
