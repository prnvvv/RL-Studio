from __future__ import annotations

import sqlite3
from typing import Any

from backend.database.connection import Database
from backend.database.exceptions import ArtifactPathError as BaseArtifactPathError
from backend.database.paths import normalize_artifact_path, resolve_artifact_path
from backend.database.repositories import artifacts as artifacts_repo
from backend.database.repositories import audit as audit_repo
from backend.database.repositories import incidents as incidents_repo
from backend.database.repositories import runs as runs_repo
from backend.database.utils import (
    new_id,
    sha256_file,
    to_iso,
    unique_preserving_order,
    validate_sha256,
)

from .exceptions import (
    ArtifactAlreadyExistsError,
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ProvenanceConflictError,
    RunNotFoundError,
    UnsafeArtifactPathError,
)
from .models import (
    ArtifactRegistration,
    ArtifactType,
    IncidentRegistration,
    RunRegistration,
)


def _audit(
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    status: str,
    correlation_id: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    audit_repo.append_audit(
        conn,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        status=status,
        correlation_id=correlation_id,
        details=details,
    )


def load_incident(
    conn: sqlite3.Connection, incident_id: str
) -> dict[str, Any] | None:
    incident = incidents_repo.get_incident(conn, incident_id)
    if incident is None:
        return None
    fault = incidents_repo.get_incident_fault(conn, incident_id) or {}
    return {
        **incident,
        "source_environment_version": fault.get("source_environment_version"),
        "corruption_start_timestep": fault.get("corruption_start_timestep"),
        "corruption_end_timestep": fault.get("corruption_end_timestep"),
        "fault_type": fault.get("fault_type"),
    }


class ArtifactRegistry:
    """Validated ingestion boundary for runs, artifacts, and incidents.

    Person 2 and Person 3 can call these methods without touching SQL.  All
    artifact paths are stored relative to the configured artifact root and
    checked before use.
    """

    def __init__(self, database: Database) -> None:
        self.database = database

    def register_run(
        self,
        request: RunRegistration,
        *,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = request.run_id or new_id("run")
        with self.database.write() as conn:
            try:
                created = runs_repo.create_run(
                    conn,
                    run_id=run_id,
                    project_id=request.project_id,
                    experiment_id=request.experiment_id,
                    environment_id=request.environment_id,
                    environment_version=request.environment_version,
                    agent_config_fingerprint=request.agent_config_fingerprint,
                    status=request.status,
                    metadata=request.metadata,
                )
            except sqlite3.IntegrityError:
                existing = runs_repo.get_run(conn, run_id)
                if existing is None:
                    raise ProvenanceConflictError("Unable to register run")
                conflicting = (
                    existing.get("environment_id") != request.environment_id
                    or existing.get("environment_version")
                    != request.environment_version
                    or (
                        request.agent_config_fingerprint is not None
                        and existing.get("agent_config_fingerprint")
                        != request.agent_config_fingerprint
                    )
                )
                if conflicting:
                    raise ProvenanceConflictError(
                        "Run is already registered with different immutable metadata",
                        details={"run_id": run_id},
                    )
                return existing
            _audit(
                conn,
                entity_type="run",
                entity_id=run_id,
                action="registered",
                status=created["status"],
                correlation_id=correlation_id,
                details={
                    "environment_id": request.environment_id,
                    "environment_version": request.environment_version,
                },
            )
            return created

    def register_artifact(
        self,
        request: ArtifactRegistration,
        *,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            artifact_path = normalize_artifact_path(request.artifact_path)
            checkpoint_path = (
                normalize_artifact_path(request.checkpoint_path)
                if request.checkpoint_path
                else None
            )
        except BaseArtifactPathError as exc:
            raise UnsafeArtifactPathError(exc.message, details=exc.details) from exc

        try:
            provided_hash = validate_sha256(request.artifact_hash)
        except ValueError as exc:
            raise ArtifactIntegrityError(str(exc)) from exc

        artifact_id = request.artifact_id or new_id("artifact")
        warnings: list[str] = []

        with self.database.write() as conn:
            run = runs_repo.get_run(conn, request.run_id)
            if run is None:
                raise RunNotFoundError(
                    "Run must be registered before its artifacts",
                    details={"run_id": request.run_id},
                )

            existing = artifacts_repo.get_artifact(conn, artifact_id)
            if existing is not None:
                same = (
                    existing["run_id"] == request.run_id
                    and existing["artifact_path"] == artifact_path
                    and existing.get("artifact_hash") == provided_hash
                )
                if same:
                    return existing
                raise ArtifactAlreadyExistsError(
                    "Artifact ID is already registered with different contents",
                    details={"artifact_id": artifact_id},
                )

            parent_id = request.parent_artifact_id
            if parent_id is not None:
                parent = artifacts_repo.get_artifact(conn, parent_id)
                if parent is None:
                    raise ArtifactNotFoundError(
                        "Parent artifact does not exist",
                        details={"parent_artifact_id": parent_id},
                    )
                if parent["run_id"] != request.run_id:
                    raise ProvenanceConflictError(
                        "Parent artifact belongs to a different run",
                        details={"parent_artifact_id": parent_id},
                    )

            absolute_path = resolve_artifact_path(
                self.database.config.artifact_root, artifact_path
            )
            integrity_status = "missing"
            content_hash = provided_hash
            requested_status = (
                request.artifact_status.value if request.artifact_status else None
            )
            if absolute_path.is_file():
                if absolute_path.stat().st_size > self.database.config.max_artifact_bytes:
                    raise UnsafeArtifactPathError(
                        "Artifact exceeds the configured size limit",
                        details={"artifact_path": artifact_path},
                    )
                actual_hash = sha256_file(absolute_path)
                if provided_hash is not None and provided_hash != actual_hash:
                    raise ArtifactIntegrityError(
                        "Artifact content hash does not match the supplied hash",
                        details={
                            "artifact_id": artifact_id,
                            "expected": provided_hash,
                            "actual": actual_hash,
                        },
                    )
                content_hash = actual_hash
                integrity_status = "verified"
                artifact_status = requested_status or "available"
            else:
                warnings.append(
                    f"Artifact file is not present under the artifact root: {artifact_path}"
                )
                artifact_status = (
                    requested_status
                    if requested_status in {"deleted", "superseded", "invalid"}
                    else "missing"
                )

            checkpoint_id = request.checkpoint_id
            if request.artifact_type is ArtifactType.checkpoint:
                checkpoint_id = checkpoint_id or artifact_id
                checkpoint_path = checkpoint_path or artifact_path

            created = artifacts_repo.create_artifact(
                conn,
                artifact_id=artifact_id,
                run_id=request.run_id,
                artifact_type=request.artifact_type.value,
                artifact_path=artifact_path,
                artifact_hash=content_hash,
                artifact_version=request.artifact_version,
                artifact_status=artifact_status,
                integrity_status=integrity_status,
                artifact_created_at=to_iso(request.artifact_created_at),
                parent_artifact_id=parent_id,
                checkpoint_id=checkpoint_id,
                checkpoint_path=checkpoint_path,
                policy_version=request.policy_version,
                trajectory_id=request.trajectory_id,
                experience_id=request.experience_id,
                policy_update_id=request.policy_update_id,
                environment_id=request.environment_id or run.get("environment_id"),
                environment_version=(
                    request.environment_version or run.get("environment_version")
                ),
                agent_config_fingerprint=(
                    request.agent_config_fingerprint
                    or run.get("agent_config_fingerprint")
                ),
                episode_id=request.episode_id,
                timestep=request.timestep,
                update_index=request.update_index,
                included_state_components=request.included_state_components,
                metadata_schema_version=request.metadata_schema_version,
                metadata=request.metadata,
            )
            if parent_id is not None:
                artifacts_repo.create_link(
                    conn,
                    run_id=request.run_id,
                    from_artifact_id=parent_id,
                    to_artifact_id=artifact_id,
                    relation="parent",
                )
            _audit(
                conn,
                entity_type="artifact",
                entity_id=artifact_id,
                action="registered",
                status=created["artifact_status"],
                correlation_id=correlation_id,
                details={
                    "run_id": request.run_id,
                    "artifact_type": request.artifact_type.value,
                    "artifact_hash": content_hash,
                    "integrity_status": integrity_status,
                    "warnings": warnings,
                },
            )
            created = {**created, "warnings": warnings}
            return created

    def register_incident(
        self,
        request: IncidentRegistration,
        *,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        with self.database.write() as conn:
            run = runs_repo.get_run(conn, request.run_id)
            if run is None:
                raise RunNotFoundError(
                    "Incident run must be registered first",
                    details={"run_id": request.run_id},
                )
            existing = incidents_repo.get_incident(conn, request.incident_id)
            if existing is not None:
                if (
                    existing["run_id"] != request.run_id
                    or existing.get("verification_id") != request.verification_id
                ):
                    raise ProvenanceConflictError(
                        "Incident ID is already registered with different references",
                        details={"incident_id": request.incident_id},
                    )
                return load_incident(conn, request.incident_id)  # type: ignore[return-value]

            incidents_repo.create_incident(
                conn,
                incident_id=request.incident_id,
                run_id=request.run_id,
                verification_id=request.verification_id,
                environment_id=request.environment_id or run.get("environment_id"),
                environment_version=(
                    request.environment_version or run.get("environment_version")
                ),
                requirement_id=request.requirement_id,
                status=request.status,
                severity=request.severity,
                detection_method=request.detection_method,
                summary=request.summary,
                evidence_ids=unique_preserving_order(request.evidence_ids),
                details=request.details,
            )
            if any(
                value is not None
                for value in (
                    request.source_environment_version,
                    request.corruption_start_timestep,
                    request.corruption_end_timestep,
                    request.fault_type,
                )
            ):
                incidents_repo.set_incident_fault(
                    conn,
                    incident_id=request.incident_id,
                    source_environment_version=request.source_environment_version,
                    corruption_start_timestep=request.corruption_start_timestep,
                    corruption_end_timestep=request.corruption_end_timestep,
                    fault_type=request.fault_type,
                )
            _audit(
                conn,
                entity_type="incident",
                entity_id=request.incident_id,
                action="registered",
                status=request.status,
                correlation_id=correlation_id,
                details={
                    "run_id": request.run_id,
                    "verification_id": request.verification_id,
                    "requirement_id": request.requirement_id,
                },
            )
            return load_incident(conn, request.incident_id)  # type: ignore[return-value]

    def record_artifact_link(
        self,
        *,
        run_id: str,
        from_artifact_id: str,
        to_artifact_id: str,
        relation: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        if not relation.strip():
            raise ProvenanceConflictError("Link relation must not be empty")
        with self.database.write() as conn:
            source = artifacts_repo.get_artifact(conn, from_artifact_id)
            target = artifacts_repo.get_artifact(conn, to_artifact_id)
            if source is None or target is None:
                raise ArtifactNotFoundError("Both link endpoints must exist")
            if source["run_id"] != run_id or target["run_id"] != run_id:
                raise ProvenanceConflictError(
                    "Linked artifacts must belong to the stated run"
                )
            link = artifacts_repo.create_link(
                conn,
                run_id=run_id,
                from_artifact_id=from_artifact_id,
                to_artifact_id=to_artifact_id,
                relation=relation,
            )
            _audit(
                conn,
                entity_type="artifact_link",
                entity_id=link["link_id"],
                action="registered",
                status="linked",
                correlation_id=correlation_id,
                details={
                    "run_id": run_id,
                    "from_artifact_id": from_artifact_id,
                    "to_artifact_id": to_artifact_id,
                    "relation": relation,
                },
            )
            return link
