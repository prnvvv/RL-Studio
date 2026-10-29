"""Stable Person 4 exception vocabulary.

Every exception carries a machine-readable ``error_code``, an HTTP status for
the API boundary, a safe message, and optional structured details.  Internal
diagnostics and secrets must not be placed in ``message``.
"""

from __future__ import annotations

import uuid
from typing import Any


class StudioError(Exception):
    error_code: str = "P4-000"
    http_status: int = 500

    def __init__(
        self,
        message: str = "An unexpected persistence error occurred",
        details: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.correlation_id = correlation_id or str(uuid.uuid4())

    def __str__(self) -> str:
        return f"{self.message} [code={self.error_code}]"


class ValidationError(StudioError):
    error_code = "P4-001"
    http_status = 422


class NotFoundError(StudioError):
    error_code = "P4-002"
    http_status = 404


class ConflictError(StudioError):
    error_code = "P4-003"
    http_status = 409


class OperationLockedError(StudioError):
    error_code = "P4-004"
    http_status = 409


class IntegrityFailure(StudioError):
    error_code = "P4-005"
    http_status = 409


class BlockedOperationError(StudioError):
    error_code = "P4-006"
    http_status = 409


class DatabaseError(StudioError):
    error_code = "P4-010"
    http_status = 500


class MigrationError(DatabaseError):
    error_code = "P4-011"
    http_status = 500


class ArtifactPathError(ValidationError):
    error_code = "P4-012"


class ArtifactHashError(IntegrityFailure):
    error_code = "P4-013"
