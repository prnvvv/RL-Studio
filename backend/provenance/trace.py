from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any

from backend.database.connection import Database
from backend.database.repositories import artifacts as artifacts_repo
from backend.database.repositories import provenance as provenance_repo
from backend.database.repositories import runs as runs_repo

from .exceptions import ArtifactNotFoundError, RunNotFoundError
from .models import Artifact, ArtifactLink, ProvenanceTrace


class ProvenanceTracer:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _build_trace(
        self,
        conn: sqlite3.Connection,
        *,
        run: dict[str, Any],
        artifacts: list[dict[str, Any]],
        links: list[dict[str, Any]],
    ) -> dict[str, Any]:
        warnings: list[str] = []
        artifact_ids = {artifact["artifact_id"] for artifact in artifacts}
        broken_parent = False
        broken_link = False

        for artifact in artifacts:
            if artifact["artifact_status"] in {"missing", "invalid", "deleted"}:
                warnings.append(
                    f"Artifact {artifact['artifact_id']} has status "
                    f"{artifact['artifact_status']}"
                )
            if not artifact.get("environment_version"):
                warnings.append(
                    f"Artifact {artifact['artifact_id']} has no recorded "
                    "environment version"
                )
            if artifact["artifact_type"] == "checkpoint" and (
                artifact.get("timestep") is None
                and artifact.get("update_index") is None
            ):
                warnings.append(
                    f"Checkpoint {artifact['artifact_id']} has no recorded "
                    "timestep/update association"
                )
            parent = artifact.get("parent_artifact_id")
            if parent is not None and parent not in artifact_ids:
                broken_parent = True
                warnings.append(
                    f"Artifact {artifact['artifact_id']} references missing "
                    f"parent {parent}"
                )

        for link in links:
            if (
                link["from_artifact_id"] not in artifact_ids
                or link["to_artifact_id"] not in artifact_ids
            ):
                broken_link = True
                warnings.append(
                    f"Link {link['link_id']} references an artifact outside the run"
                )

        environment_versions = sorted(
            {
                artifact["environment_version"]
                for artifact in artifacts
                if artifact.get("environment_version")
            }
        )
        if len(environment_versions) > 1:
            warnings.append(
                "Multiple environment versions are recorded in this run: "
                + ", ".join(environment_versions)
            )

        missing_lineage = any(
            not artifact.get("environment_version")
            or artifact["artifact_status"] in {"missing", "invalid", "deleted"}
            or (
                artifact["artifact_type"] == "checkpoint"
                and artifact.get("timestep") is None
                and artifact.get("update_index") is None
            )
            for artifact in artifacts
        )

        if not artifacts:
            lineage_completeness = "unknown"
            provenance_status = "unknown"
            warnings.append("No artifacts are recorded for this run")
        elif broken_parent or broken_link:
            lineage_completeness = "partial"
            provenance_status = "conflict"
        elif missing_lineage:
            lineage_completeness = "partial"
            provenance_status = "incomplete"
        else:
            lineage_completeness = "complete"
            provenance_status = "complete"

        artifact_types = Counter(artifact["artifact_type"] for artifact in artifacts)
        details = {
            "artifact_types": dict(sorted(artifact_types.items())),
            "environment_versions": environment_versions,
            "association_gap_count": sum(
                1
                for artifact in artifacts
                if not artifact.get("environment_version")
                or artifact["artifact_status"] in {"missing", "invalid", "deleted"}
                or (
                    artifact["artifact_type"] == "checkpoint"
                    and artifact.get("timestep") is None
                    and artifact.get("update_index") is None
                )
            ),
        }
        evidence_ids = sorted(
            {
                evidence_id
                for artifact in artifacts
                for evidence_id in artifact.get("metadata", {}).get("evidence_ids", [])
                if isinstance(evidence_id, str)
            }
        )

        return provenance_repo.upsert_provenance_record(
            conn,
            run_id=run["run_id"],
            provenance_status=provenance_status,
            lineage_completeness=lineage_completeness,
            source_environment_version=run.get("environment_version"),
            artifact_count=len(artifacts),
            warnings=warnings,
            evidence_ids=evidence_ids,
            details=details,
        )

    def get_run_provenance(self, run_id: str) -> ProvenanceTrace:
        with self.database.write() as conn:
            run = runs_repo.get_run(conn, run_id)
            if run is None:
                raise RunNotFoundError(
                    "Run was not found", details={"run_id": run_id}
                )
            artifact_rows = artifacts_repo.list_artifacts_for_run(conn, run_id)
            link_rows = artifacts_repo.list_links_for_run(conn, run_id)
            record = self._build_trace(
                conn, run=run, artifacts=artifact_rows, links=link_rows
            )
            artifacts = [Artifact.model_validate(row) for row in artifact_rows]
            links = [ArtifactLink.model_validate(row) for row in link_rows]
            return ProvenanceTrace.model_validate(
                {
                    **record,
                    "environment_id": run.get("environment_id"),
                    "environment_version": run.get("environment_version"),
                    "artifacts": artifacts,
                    "links": links,
                }
            )

    def list_run_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            if runs_repo.get_run(conn, run_id) is None:
                raise RunNotFoundError(
                    "Run was not found", details={"run_id": run_id}
                )
            return artifacts_repo.list_artifacts_for_run(conn, run_id)

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        with self.database.read() as conn:
            artifact = artifacts_repo.get_artifact(conn, artifact_id)
        if artifact is None:
            raise ArtifactNotFoundError(
                "Artifact was not found", details={"artifact_id": artifact_id}
            )
        return artifact
