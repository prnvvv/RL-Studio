"""Evaluation exceptions."""

from __future__ import annotations

from backend.database.exceptions import StudioError


class EvaluationError(StudioError):
    http_status = 400
    error_code = "EVAL-000"


class EvaluationNotFoundError(EvaluationError):
    http_status = 404
    error_code = "EVAL-002"


class EvaluationBlockedError(EvaluationError):
    http_status = 409
    error_code = "EVAL-003"


class EvaluationConflictError(EvaluationError):
    http_status = 409
    error_code = "EVAL-004"


class EvaluationValidationError(EvaluationError):
    http_status = 422
    error_code = "EVAL-001"


class InvalidEvaluationStateError(EvaluationError):
    http_status = 409
    error_code = "EVAL-005"


class BaselineNotFoundError(EvaluationNotFoundError):
    error_code = "EVAL-006"


class MissingEvaluationMetricsError(EvaluationValidationError):
    error_code = "EVAL-007"
