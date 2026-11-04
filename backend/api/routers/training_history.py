"""Project-scoped training history: agents, environments, experiments and the training-run catalog.

Authorization is the project in the path: it must exist, and a request scope header naming a different project is
refused. Every run, entity and evidence lookup is then filtered by that project, and a missing record and another
project's record produce the identical 404, so ids are never an oracle. Lists are paginated; per-episode data is paged
and trajectories (steps) are not part of any summary or detail response.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.database.repositories import incidents as incidents_repo
from backend.database.repositories import recoveries as recoveries_repo
from backend.diagnosis.store import InvestigationStore
from backend.events.service import EventPublisher
from backend.projects.repository import ProjectRepository
from backend.projects.scope import requested_scope
from backend.studio.session import store_path
from backend.studio.store import TrajectoryReader
from backend.training_history import TrainingHistory
from backend.training_history.service import MAX_PAGE, HistoryError, NotFound
from backend.verification.storage.sqlite_store import SqliteVerificationStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["training-history"])

ProjectId = Annotated[str, Path(pattern=r"^prj_[0-9a-f]{16}$")]
EntityId = Annotated[str, Path(pattern=r"^[a-z]{3}_[0-9a-f]{12}$")]
RunIdPath = Annotated[str, Path(pattern=r"^[A-Za-z0-9_.:\-]{1,128}$")]


class AgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    algorithm: str = Field(min_length=1, max_length=32)
    params: dict[str, Any] = Field(default_factory=dict)


class EnvironmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    environment: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)


class Rename(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)


class ExperimentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=1000)


def _error(exc: HistoryError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})


def _history(request: Request, project_id: str) -> TrainingHistory | JSONResponse:
    database = getattr(request.app.state, "database", None)
    if database is None:
        return JSONResponse(status_code=503, content={"error": {"code": "unavailable", "message": "The application is not ready."}})
    scope = requested_scope(request)
    if (scope is not None and scope != project_id) or ProjectRepository(database).get_project(project_id) is None:
        return _error(NotFound("project not found"))
    return TrainingHistory(database)


def _not_found(what: str) -> JSONResponse:
    return _error(NotFound(f"{what} not found in this project"))


# ----------------------------------------------------------------------------------------- entities
@router.get("/agents")
def list_agents(project_id: ProjectId, request: Request) -> Any:
    hist = _history(request, project_id)
    if isinstance(hist, JSONResponse):
        return hist
    items = hist.list_agents(project_id)
    return {"count": len(items), "agents": items}


@router.post("/agents", status_code=201)
def create_agent(project_id: ProjectId, body: AgentCreate, request: Request) -> Any:
    hist = _history(request, project_id)
    return hist if isinstance(hist, JSONResponse) else hist.create_agent(
        project_id, name=body.name, algorithm=body.algorithm, params=body.params)


@router.patch("/agents/{agent_id}")
def rename_agent(project_id: ProjectId, agent_id: EntityId, body: Rename, request: Request) -> Any:
    hist = _history(request, project_id)
    if isinstance(hist, JSONResponse):
        return hist
    try:
        hist.rename(project_id, "project_agents", "agent_id", agent_id, body.name)
    except HistoryError as exc:
        return _error(exc)
    return next(a for a in hist.list_agents(project_id) if a["agent_id"] == agent_id)


@router.get("/environments")
def list_environments(project_id: ProjectId, request: Request) -> Any:
    hist = _history(request, project_id)
    if isinstance(hist, JSONResponse):
        return hist
    items = hist.list_environments(project_id)
    return {"count": len(items), "environments": items}


@router.post("/environments", status_code=201)
def create_environment(project_id: ProjectId, body: EnvironmentCreate, request: Request) -> Any:
    hist = _history(request, project_id)
    return hist if isinstance(hist, JSONResponse) else hist.create_environment(
        project_id, name=body.name, environment=body.environment, params=body.params)


@router.patch("/environments/{environment_config_id}")
def rename_environment(project_id: ProjectId, environment_config_id: EntityId, body: Rename, request: Request) -> Any:
    hist = _history(request, project_id)
    if isinstance(hist, JSONResponse):
        return hist
    try:
        hist.rename(project_id, "project_environment_configs", "environment_config_id", environment_config_id, body.name)
    except HistoryError as exc:
        return _error(exc)
    return next(e for e in hist.list_environments(project_id) if e["environment_config_id"] == environment_config_id)


@router.get("/experiments")
def list_experiments(project_id: ProjectId, request: Request) -> Any:
    hist = _history(request, project_id)
    if isinstance(hist, JSONResponse):
        return hist
    items = hist.list_experiments(project_id)
    return {"count": len(items), "experiments": items}


@router.post("/experiments", status_code=201)
def create_experiment(project_id: ProjectId, body: ExperimentCreate, request: Request) -> Any:
    hist = _history(request, project_id)
    return hist if isinstance(hist, JSONResponse) else hist.create_experiment(
        project_id, name=body.name, description=body.description)


@router.get("/experiments/{experiment_id}/runs")
def experiment_runs(project_id: ProjectId, experiment_id: EntityId, request: Request,
                    limit: int = Query(50, ge=1, le=MAX_PAGE), offset: int = Query(0, ge=0)) -> Any:
    hist = _history(request, project_id)
    if isinstance(hist, JSONResponse):
        return hist
    if not any(x["experiment_id"] == experiment_id for x in hist.list_experiments(project_id)):
        return _not_found("experiment")
    return hist.list_runs(project_id, experiment_id=experiment_id, limit=limit, offset=offset)


# ------------------------------------------------------------------------------------------- runs
@router.get("/training-runs")
def list_training_runs(
    project_id: ProjectId, request: Request,
    agent_id: str | None = Query(None, max_length=40), environment_config_id: str | None = Query(None, max_length=40),
    experiment_id: str | None = Query(None, max_length=40), status: str | None = Query(None, max_length=20),
    q: str | None = Query(None, max_length=80), sort: str = Query("recent", pattern="^(recent|oldest|timesteps)$"),
    limit: int = Query(50, ge=1, le=MAX_PAGE), offset: int = Query(0, ge=0),
) -> Any:
    hist = _history(request, project_id)
    if isinstance(hist, JSONResponse):
        return hist
    return hist.list_runs(project_id, agent_id=agent_id, environment_config_id=environment_config_id,
                          experiment_id=experiment_id, status=status, q=q, sort=sort, limit=limit, offset=offset)


@router.get("/training-runs/latest")
def latest_training_run(project_id: ProjectId, request: Request, agent_id: str | None = Query(None, max_length=40)) -> Any:
    hist = _history(request, project_id)
    if isinstance(hist, JSONResponse):
        return hist
    return {"run": hist.latest_run(project_id, agent_id=agent_id)}


@router.get("/training-runs/compare")
def compare_runs(project_id: ProjectId, request: Request, run_ids: str = Query(..., max_length=600)) -> Any:
    hist = _history(request, project_id)
    if isinstance(hist, JSONResponse):
        return hist
    ids = [r.strip() for r in run_ids.split(",") if r.strip()][:6]
    try:
        return hist.compare(project_id, ids)
    except HistoryError as exc:
        return _error(exc)


def _run_or_404(request: Request, project_id: str, run_id: str) -> tuple[TrainingHistory, dict[str, Any]] | JSONResponse:
    hist = _history(request, project_id)
    if isinstance(hist, JSONResponse):
        return hist
    run = hist.get_run(project_id, run_id)
    return _not_found("run") if run is None else (hist, run)


@router.get("/training-runs/{run_id}")
def get_training_run(project_id: ProjectId, run_id: RunIdPath, request: Request) -> Any:
    found = _run_or_404(request, project_id, run_id)
    if isinstance(found, JSONResponse):
        return found
    hist, run = found
    database = request.app.state.database
    reader = TrajectoryReader(store_path())
    with database.read() as conn:
        incidents = incidents_repo.list_incidents_for_run(conn, run_id)
        recoveries = [r for i in incidents for r in recoveries_repo.list_recoveries_for_incident(conn, i["incident_id"])]
    store = InvestigationStore(database)
    verifications = SqliteVerificationStore(database).list_verifications(run_id)
    return {
        "run": run,
        "snapshots": hist.snapshots(run_id),
        "checkpoints": reader.checkpoints(run_id) if reader.get_run(run_id) else [],
        # Policy evaluations of this run's saved checkpoints (append-only; episodes omitted, fetch one for them).
        "evaluations": request.app.state.services.run_evaluation.list_for_run(run_id),
        "verifications": [{"verification_id": v["verification_id"], "overall_status": v["overall_status"],
                           "created_at": v["created_at"]} for v in verifications],
        "incidents": [{"incident_id": i["incident_id"], "status": i["status"], "severity": i.get("severity"),
                       "summary": i.get("summary"), "created_at": i["created_at"],
                       "investigations": len(store.list_for_incident(i["incident_id"]))} for i in incidents],
        "recoveries": [{"recovery_id": r["recovery_id"], "incident_id": r["incident_id"],
                        "recovery_status": r["recovery_status"], "recovery_strategy": r["recovery_strategy"],
                        "created_at": r["created_at"]} for r in recoveries],
    }


@router.get("/training-runs/{run_id}/metrics")
def training_run_metrics(project_id: ProjectId, run_id: RunIdPath, request: Request,
                         offset: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=MAX_PAGE)) -> Any:
    """Persisted metrics for any run (finished, stopped, failed or live): a page of episodes plus the update and
    evaluation series. Nothing is synthesised: a run with no episodes returns empty lists."""
    found = _run_or_404(request, project_id, run_id)
    if isinstance(found, JSONResponse):
        return found
    _, run = found
    reader = TrajectoryReader(store_path())
    stored = reader.get_run(run_id)
    return {
        "run_id": run_id, "status": run["status"], "final_metrics": run["final_metrics"],
        "total_timesteps": run["total_timesteps"], "total_episodes": run["total_episodes"],
        "episodes_total": stored["episode_count"] if stored else 0, "offset": offset, "limit": limit,
        "episodes": reader.episodes(run_id, offset, limit) if stored else [],
        "updates": reader.table(run_id, "updates", 0, limit) if stored else [],
        "evaluations": reader.table(run_id, "evaluations", 0, limit) if stored else [],
        "available": stored is not None,
    }


@router.get("/training-runs/{run_id}/events")
def training_run_events(project_id: ProjectId, run_id: RunIdPath, request: Request,
                        offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=MAX_PAGE)) -> Any:
    found = _run_or_404(request, project_id, run_id)
    if isinstance(found, JSONResponse):
        return found
    try:
        events = [e.model_dump(mode="json") for e in EventPublisher.list_run_events(run_id)]
    except Exception:  # noqa: BLE001 - the event log is optional evidence
        logger.warning("run events unavailable for %s", run_id)
        events = []
    return {"run_id": run_id, "total": len(events), "offset": offset, "events": events[offset: offset + limit]}


@router.get("/training-runs/{run_id}/checkpoints")
def training_run_checkpoints(project_id: ProjectId, run_id: RunIdPath, request: Request) -> Any:
    found = _run_or_404(request, project_id, run_id)
    if isinstance(found, JSONResponse):
        return found
    reader = TrajectoryReader(store_path())
    return {"run_id": run_id, "checkpoints": reader.checkpoints(run_id) if reader.get_run(run_id) else []}
