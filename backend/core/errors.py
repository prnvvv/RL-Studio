"""Typed error categories."""
from __future__ import annotations

from typing import Any


class APIError(Exception):
    def __init__(self, message: str, status_code: int = 500, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class ValidationError(APIError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, status_code=400, details=details)


class NotFoundError(APIError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, status_code=404, details=details)


class ConflictError(APIError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, status_code=409, details=details)


class BlockedError(APIError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, status_code=409, details=details)


class UnauthorizedError(APIError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, status_code=401, details=details)


class TimeoutError(APIError):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message, status_code=504, details=details)
