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
