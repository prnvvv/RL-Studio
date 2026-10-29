from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI

from backend.database.config import DatabaseConfig
from backend.database.connection import Database

from .dependencies import build_services
from .errors import install_error_handlers
from .routers import evaluation, provenance, recovery


def create_app(config: Optional[DatabaseConfig] = None) -> FastAPI:
    database_config = config

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = Database(database_config or DatabaseConfig.from_env())
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
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.include_router(provenance.p4_router)
    app.include_router(recovery.p4_router)
    app.include_router(evaluation.p4_router)
    return app


try:
    from .routers import runs

    app.include_router(runs.router)
except Exception:
    pass


# Real-time updates channel (WebSocket + SSE)
try:
    from .routers.ws_events import router as ws_router
    app.include_router(ws_router)
except Exception:
    pass
