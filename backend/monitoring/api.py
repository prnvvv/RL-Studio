"""Monitoring API endpoints."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from backend.monitoring.exceptions import MetricValidationError

router = APIRouter(prefix="/api/v1", tags=["monitoring"])


@router.get("/metrics/health")
async def metrics_health() -> Dict[str, Any]:
    return {"status": "ok"}


@router.post("/metrics/validate", response_model=Dict[str, str])
async def validate_metrics(data: Dict[str, Any]) -> Dict[str, str]:
    return {"status": "validated"}
