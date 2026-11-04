"""Diagnosis API helpers."""
from __future__ import annotations

from typing import Any


def get_diagnosis_status(provider_configured: bool) -> dict[str, Any]:
    if not provider_configured:
        return {"status": "provider_unavailable", "message": "Grok/xAI provider not configured", "diagnosis": None}
    return {"status": "ready", "provider_configured": True}
