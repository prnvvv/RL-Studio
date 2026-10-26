from __future__ import annotations

from backend.database.exceptions import (
    BlockedOperationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)


class RecoveryError(ValidationError):
    error_code = "RECOV-000"


class RecoveryNotFoundError(NotFoundError):
    error_code = "RECOV-001"


class AssessmentNotFoundError(NotFoundError):
    error_code = "RECOV-002"


class RecoveryBlockedError(BlockedOperationError):
    error_code = "RECOV-003"


class RecoveryConflictError(ConflictError):
    error_code = "RECOV-004"
