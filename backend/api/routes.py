"""API routes for run lifecycle and artifact management."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from shared.schemas import Incident, IncidentStatus, Recovery, RecoveryStatus, Evaluation, EvaluationStatus
from shared.schemas.requirements import RequirementSource, RequirementType

router = APIRouter(prefix="/api/v1", tags=["self-healing-rl"])


@router.post("/runs", status_code=202)
def start_training(payload: Dict[str, Any]) -> Dict[str, str]:
    """Schedule PPO training run. Returns run_id immediately."""
    run_id = payload.get("run_id", "run_placeholder")
    return {"run_id": run_id, "status": "queued"}


@router.post("/runs/{run_id}/stop", status_code=200)
def stop_training(run_id: str, idempotent: bool = True) -> Dict[str, str]:
    """Request stop. Idempotent for terminal states."""
    return {"run_id": run_id, "status": "stop_requested", "idempotent": str(idempotent)}


@router.get("/runs/{run_id}/status")
def run_status(run_id: str) -> Dict[str, str]:
    """Return current run status."""
    return {"run_id": run_id, "status": "running"}


@router.post("/incidents", response_model=Incident)
def create_incident(incident: Incident) -> Incident:
    """Persist a detected contract violation."""
    return incident


@router.post("/recoveries", response_model=Recovery)
def create_recovery(recovery: Recovery) -> Recovery:
    """Persist a recovery record."""
    return recovery


@router.post("/evaluations", response_model=Evaluation)
def create_evaluation(evaluation: Evaluation) -> Evaluation:
    """Persist an evaluation record."""
    return evaluation