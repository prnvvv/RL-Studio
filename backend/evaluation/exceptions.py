from __future__ import annotations

from backend.database.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)


class EvaluationError(ValidationError):
    error_code = "EVAL-000"


class EvaluationValidationError(EvaluationError):
    error_code = "EVAL-001"


class EvaluationNotFoundError(NotFoundError):
    error_code = "EVAL-002"


class EvaluationConflictError(ConflictError):
    error_code = "EVAL-003"
