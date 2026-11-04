from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.database.config import DatabaseConfig
from backend.database.connection import Database
from backend.projects.scope import enforce_project_scope
from backend.verification.incidents.sink import ProvenanceIncidentSink
from backend.workflow import WorkflowAutomation

from .dependencies import build_services
from .errors import install_error_handlers
from .routers import (
    assistant,
    diagnosis,
    evaluation,
    incidents,
    projects,
    provenance,
    recovery,
    runs,
    studio,
    training_history,
    verification,
    voice,
)
from .routers.ws_events import router as ws_router

logger = logging.getLogger(__name__)


def _reconcile_training_history(database: Database) -> None:
    """A run still marked active that is not alive in this process was abandoned: record it as interrupted."""
    try:
        from backend.studio.manager import manager
        from backend.training_history import TrainingHistory

        fixed = TrainingHistory(database).reconcile(manager.active_run_ids())
        if fixed:
            logger.warning("marked %d abandoned training run(s) as interrupted", len(fixed))
    except Exception:
        logger.exception("training history reconciliation failed")


def _install_automation(app: FastAPI, database: Database) -> WorkflowAutomation:
    """Wire the optional event-driven steps (``RL_STUDIO_AUTO_EVALUATE`` / ``RL_STUDIO_AUTO_INVESTIGATE``)."""
    services = app.state.services

    def evaluate(run_id: str) -> None:
        services.run_evaluation.evaluate(run_id, purpose="auto_on_completion")

    def investigate(incident_id: str) -> None:
        from backend.ai.service import get_ai_service
        from backend.diagnosis.service import DiagnosisService

        ai = getattr(app.state, "ai_service", None) or get_ai_service()
        diagnosis = DiagnosisService(database, services.provenance, ai)
        diagnosis.investigate(incident_id)
        diagnosis.recommend_recovery(incident_id)  # a plan for every incident, never executed

    automation = WorkflowAutomation(evaluate=evaluate, investigate=investigate)
    automation.install()
    if automation.auto_investigate and getattr(app.state, "verification_incident_sink", None) is None:
        app.state.verification_incident_sink = automation.wrap_sink(ProvenanceIncidentSink(services.provenance))
    return automation


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
        _reconcile_training_history(database)
        automation = _install_automation(app, database)
        try:
            yield
        finally:
            automation.uninstall()

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_error_handlers(app)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "app": "Self-Healing RL Studio API"}

    @app.get("/v1/models", include_in_schema=False)
    async def list_models_probe() -> dict[str, object]:
        # Local tools that treat this port as an OpenAI-compatible server probe this path.
        # RL Studio serves no models here, so answer with an empty list instead of a 404.
        return {"object": "list", "data": []}

    # Every router that exposes run-owned data enforces project isolation on the server
    # (``backend/projects/scope.py``). The projects router is authorised by its own path project id.
    scoped = [Depends(enforce_project_scope)]

    # Documented Person 4 contract endpoints.
    app.include_router(provenance.p4_router, dependencies=scoped)
    app.include_router(recovery.p4_router, dependencies=scoped)
    app.include_router(evaluation.p4_router, dependencies=scoped)
    app.include_router(verification.router, dependencies=scoped)
    # Advisory diagnosis is operational (not a documented Person 4 contract endpoint): kept out of the schema.
    app.include_router(diagnosis.router, include_in_schema=False, dependencies=scoped)
    app.include_router(incidents.router, include_in_schema=False, dependencies=scoped)

    # Operational endpoints are wired but kept out of the documented schema.
    app.include_router(runs.router, include_in_schema=False, dependencies=scoped)
    app.include_router(ws_router, include_in_schema=False, dependencies=scoped)
    app.include_router(studio.router, include_in_schema=False, dependencies=scoped)
    app.include_router(projects.router, include_in_schema=False)
    # Authorised by the project id in the path (existing, non-deleted, and any scope header must match it).
    app.include_router(training_history.router, include_in_schema=False)
    app.include_router(voice.router, include_in_schema=False)
    # The assistant checks the run/incident named in its body against the validated project scope itself.
    app.include_router(assistant.router, include_in_schema=False)
    return app


app = create_app()
