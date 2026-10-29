"""Runs/projects/experiments API."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from backend.workers.training_worker import worker

router = APIRouter(prefix="/api/v1", tags=["runs"])


@router.post("/runs/start")
async def start_run(config: Dict[str, Any]) -> Dict[str, Any]:
    run_id = config.get("run_id") or "run_default"
    def _do():
        return {"run_id": run_id, "started": True}
    worker.submit(run_id, _do)
    return {"run_id": run_id, "status": "queued"}


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str) -> Dict[str, Any]:
    return {"run_id": run_id, "status": "stop_requested", "idempotent": True}


@router.get("/runs/{run_id}/status")
async def get_run_status(run_id: str) -> Dict[str, Any]:
    return worker.status(run_id)