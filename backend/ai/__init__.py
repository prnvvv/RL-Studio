"""Hosted AI foundation: Meta Model API is the only inference provider. No local inference."""

from .service import AIService, get_ai_service
from .settings import AISettings

__all__ = ["AIService", "AISettings", "get_ai_service"]
