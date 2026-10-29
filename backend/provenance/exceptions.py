"""Provenance exceptions."""

from __future__ import annotations

from backend.database.exceptions import (
    ConflictError,
    IntegrityFailure,
    NotFoundError,
    StudioError,
    ValidationError,
)


class ProvenanceError(StudioError):
    http_status = 400
    error_code = "PROV-000"


class RunNotFoundError(NotFoundError):
    error_code = "PROV-002"


class IncidentNotFoundError(NotFoundError):
    error_code = "PROV-003"


class ArtifactNotFoundError(NotFoundError):
    error_code = "PROV-002"


class ArtifactIntegrityError(IntegrityFailure):
    error_code = "PROV-005"


class UnsafeArtifactPathError(ValidationError):
    error_code = "PROV-006"


class ProvenanceConflictError(ConflictError):
    error_code = "PROV-007"


class ProvenanceValidationError(ProvenanceError):
    http_status = 422
    error_code = "PROV-001"


class ArtifactAlreadyExistsError(ConflictError):
    error_code = "PROV-008"


class IncidentAlreadyExistsError(ConflictError):
    error_code = "PROV-009"


class RunAlreadyExistsError(ConflictError):
    error_code = "PROV-010"
