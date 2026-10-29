"""Monitoring API endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["monitoring"])


@router.get("/metrics/health")
async def metrics_health() -> dict[str, Any]:
    return {"status": "ok"}


@router.post("/metrics/validate", response_model=dict[str, str])
async def validate_metrics(data: dict[str, Any]) -> dict[str, str]:
    return {"status": "validated"}
