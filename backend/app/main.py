"""FastAPI application entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.core.config import settings
from backend.core.errors import APIError

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Self-Healing RL Studio API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "details": exc.details},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_name}


# Try to include verification routes if available
try:
    from backend.api import router as verification_router

    app.include_router(verification_router)
except Exception:
        logger.exception("Failed to include verification routes")

try:
    from backend.api.routers.diagnosis import router as diagnosis_router
    from backend.api.routers.evaluation import router as evaluation_router
    from backend.api.routers.provenance import router as provenance_router
    from backend.api.routers.recovery import router as recovery_router

    app.include_router(provenance_router)
    app.include_router(recovery_router)
    app.include_router(evaluation_router)
    app.include_router(diagnosis_router)
except Exception:
        logger.exception("Failed to include verification routes")
