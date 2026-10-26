from __future__ import annotations

from backend.database.exceptions import (
    ArtifactPathError,
    ConflictError,
    IntegrityFailure,
    NotFoundError,
    ValidationError,
)


class ProvenanceError(ValidationError):
    error_code = "PROV-000"


class RunNotFoundError(NotFoundError):
    error_code = "PROV-001"


class ArtifactNotFoundError(NotFoundError):
    error_code = "PROV-002"


class IncidentNotFoundError(NotFoundError):
    error_code = "PROV-003"


class ArtifactAlreadyExistsError(ConflictError):
    error_code = "PROV-004"


class ArtifactIntegrityError(IntegrityFailure):
    error_code = "PROV-005"


class UnsafeArtifactPathError(ArtifactPathError):
    error_code = "PROV-006"


class ProvenanceConflictError(ConflictError):
    error_code = "PROV-007"
