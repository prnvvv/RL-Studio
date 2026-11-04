"""Typed errors for hosted AI inference.

Messages are safe to show to API clients: they never contain credentials,
prompts, or raw provider bodies.
"""

from __future__ import annotations


class AIError(Exception):
    code = "AI-000"
    retryable = False
    http_status = 502

    def __init__(self, message: str, *, provider: str | None = None, model: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.model = model


class AIConfigurationError(AIError):
    code = "AI-001"
    http_status = 503


class AIAuthError(AIError):
    code = "AI-002"
    http_status = 502


class AIRateLimitError(AIError):
    code = "AI-003"
    retryable = True
    http_status = 429


class AITimeoutError(AIError):
    code = "AI-004"
    retryable = True
    http_status = 504


class AIProviderUnavailableError(AIError):
    code = "AI-005"
    retryable = True
    http_status = 503


class AIModelUnavailableError(AIError):
    code = "AI-006"
    http_status = 503


class AIUnsupportedTaskError(AIError):
    code = "AI-007"
    http_status = 501


class AIInvalidResponseError(AIError):
    code = "AI-008"
    http_status = 502


class AIInvalidInputError(AIError):
    code = "AI-009"
    http_status = 422


class AIPayloadTooLargeError(AIInvalidInputError):
    code = "AI-010"
    http_status = 413
