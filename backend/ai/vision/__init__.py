"""Hosted visual understanding (no local inference)."""

from .qwen_vision import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_PROMPT,
    QwenVisionClient,
)

__all__ = ["DEFAULT_BASE_URL", "DEFAULT_MODEL", "DEFAULT_PROMPT", "QwenVisionClient"]
