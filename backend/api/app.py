from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.database.config import DatabaseConfig
from backend.database.connection import Database

from .dependencies import build_services
from .errors import install_error_handlers
from .routers import evaluation, provenance, recovery, runs, verification
from .routers.ws_events import router as ws_router

logger = logging.getLogger(__name__)


def create_app(config: DatabaseConfig | None = None) -> FastAPI:
    """Build the FastAPI application.

    ``config`` defaults to the environment-derived database configuration; tests
    pass an isolated configuration.
    """
    database_config = config or DatabaseConfig.from_env()

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(database_config)
        database.initialize()
        app.state.database = database
        app.state.services = build_services(database)
        yield

    app = FastAPI(
        title="Self-Healing RL Studio API",
        version="0.1.0",
        description=(
            "Provenance, artifact exposure, controlled recovery, and "
            "evidence-based evaluation endpoints. Exposure is not proof of "
            "causal damage, and recovery execution is not recovery success."
        ),
        lifespan=_lifespan,
    )

    install_error_handlers(app)

    # Documented Person 4 contract endpoints.
    app.include_router(provenance.p4_router)
    app.include_router(recovery.p4_router)
    app.include_router(evaluation.p4_router)
    app.include_router(verification.router)

    # Operational endpoints are wired but kept out of the documented schema.
    app.include_router(runs.router, include_in_schema=False)
    app.include_router(ws_router, include_in_schema=False)
    return app


app = create_app()
