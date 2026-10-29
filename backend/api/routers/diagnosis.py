"""Diagnosis router."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from backend.core.config import settings
from backend.diagnosis.api import get_diagnosis_status

router = APIRouter(prefix="/api/v1/diagnosis", tags=["diagnosis"])


@router.get("/status")
async def diagnosis_status() -> dict[str, Any]:
    return get_diagnosis_status(bool(settings.meta_ai_api_key))


@router.post("/investigate")
async def investigate(evidence: dict[str, Any]) -> dict[str, Any]:
    if not settings.meta_ai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meta AI provider not configured; diagnosis unavailable",
        )
    return {"status": "submitted", "evidence_keys": list(evidence.keys()) if evidence else []}