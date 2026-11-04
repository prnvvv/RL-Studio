"""Hosted AI (Groq / Hugging Face) provider foundation. No local inference."""

from .service import AIService, get_ai_service
from .settings import AISettings

__all__ = ["AIService", "AISettings", "get_ai_service"]
