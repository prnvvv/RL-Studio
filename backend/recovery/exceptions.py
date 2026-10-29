"""Recovery exceptions."""

from __future__ import annotations

from backend.database.exceptions import (
    BlockedOperationError,
    ConflictError,
    IntegrityFailure,
    NotFoundError,
    StudioError,
    ValidationError,
)


class RecoveryError(StudioError):
    http_status = 400
    error_code = "REC-000"


class RecoveryAssessmentNotFoundError(NotFoundError):
    error_code = "REC-002"


class RecoveryNotFoundError(NotFoundError):
    error_code = "REC-003"


class RecoveryBlockedError(BlockedOperationError):
    error_code = "REC-004"


class RecoveryConflictError(ConflictError):
    error_code = "REC-005"


class IncompatibleCheckpointError(IntegrityFailure):
    error_code = "REC-006"


class MissingCheckpointStateError(ValidationError):
    error_code = "REC-007"


class CheckpointIntegrityFailure(IntegrityFailure):
    error_code = "REC-008"


class RecoveryValidationError(RecoveryError):
    http_status = 422
    error_code = "REC-001"


AssessmentNotFoundError = RecoveryAssessmentNotFoundError
