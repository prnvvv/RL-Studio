"""Monitoring exceptions."""

from backend.database.exceptions import StudioError


class MonitoringError(StudioError):
    http_status = 400
    error_code = "MON-000"


class MetricValidationError(MonitoringError):
    http_status = 422
    error_code = "MON-001"


class EvaluationWindowError(MonitoringError):
    http_status = 400
    error_code = "MON-002"
