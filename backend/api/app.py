from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from fastapi import FastAPI

from backend.database.config import DatabaseConfig
from backend.database.connection import Database

from .dependencies import build_services
from .errors import install_error_handlers
from .routers import evaluation, provenance, recovery, runs  # noqa: F401
from .routers.ws_events import router as ws_router  # noqa: F401

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------

database_config = DatabaseConfig.from_env()

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Self-Healing RL Studio API",
    version="0.1.0",
    description=(
        "Provenance, artifact exposure, controlled recovery, and "
        "evidence-based evaluation endpoints. Exposure is not proof of "
        "causal damage, and recovery execution is not recovery success."
    ),
)

# ---------------------------------------------------------------------------
# Lifespan context manager
# -------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    database = Database(database_config)
    database.initialize()
    app.state.database = database
    app.state.services = build_services(database)
    yield


app.lifespan(_lifespan)  # type: ignore[arg-type]

# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------

install_error_handlers(app)
app.include_router(provenance.p4_router)
app.include_router(recovery.p4_router)
app.include_router(evaluation.p4_router)
app.include_router(runs.router)
app.include_router(ws_router)  # type: ignore[arg-type]