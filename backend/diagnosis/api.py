"""Diagnosis API helpers."""
from __future__ import annotations

from typing import Any, Dict



def get_diagnosis_status(provider_configured: bool) -> Dict[str, Any]:
    if not provider_configured:
        return {"status": "provider_unavailable", "message": "Meta AI provider not configured", "diagnosis": None}
    return {"status": "ready", "provider_configured": True}
