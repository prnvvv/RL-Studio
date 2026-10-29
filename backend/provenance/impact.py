from __future__ import annotations

from collections import Counter
from typing import Any

from backend.database.connection import Database
from backend.database.repositories import artifacts as artifacts_repo
from backend.database.repositories import audit as audit_repo
from backend.database.repositories import impacts as impacts_repo
from backend.database.repositories import runs as runs_repo
from backend.database.utils import unique_preserving_order

from .exceptions import IncidentNotFoundError, RunNotFoundError
from .models import ImpactAnalysis
from .registry import load_incident

CONFIRMED = "confirmed_exposed"
POTENTIAL = "potentially_affected"
NOT_EXPOSED = "not_exposed_based_on_recorded_lineage"
UNKNOWN = "unknown_incomplete_lineage"


def _timestep(artifact: dict[str, Any]) -> int | None:
    if artifact.get("timestep") is not None:
        return int(artifact["timestep"])
    if artifact.get("update_index") is not None:
        return int(artifact["update_index"])
    return None


def _classify_initial(
    artifact: dict[str, Any],
    *,
    source_environment_version: str | None,
    start: int | None,
    end: int | None,
) -> tuple[str, str]:
    if source_environment_version is None:
        return UNKNOWN, "incident has no recorded source environment version"

    artifact_environment = artifact.get("environment_version")
    if artifact_environment is None:
        return UNKNOWN, "artifact has no recorded environment version"

    if artifact_environment != source_environment_version:
        return (
            NOT_EXPOSED,
            "artifact environment version differs from the affected version",
        )

    if start is None and end is None:
        return (
            POTENTIAL,
            (
                "artifact belongs to the affected environment but the fault "
                "interval is unknown"
            ),
        )

    timestep = _timestep(artifact)
    if timestep is None:
        return (
            UNKNOWN,
            (
                "artifact belongs to the affected environment but has no "
                "timestep/update association"
            ),
        )
    if start is not None and timestep < start:
        return NOT_EXPOSED, "artifact timestep predates the corruption interval"
    if end is not None and timestep > end:
        return NOT_EXPOSED, "artifact timestep postdates the corruption interval"
    return CONFIRMED, "artifact timestep is within the corruption interval"


class ImpactAnalyzer:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _compute(
        self,
        *,
        incident: dict[str, Any],
        artifacts: list[dict[str, Any]],
        links: list[dict[str, Any]],
    ) -> dict[str, Any]:
        source_environment_version = (
            incident.get("source_environment_version")
            or incident.get("environment_version")
        )
        start = incident.get("corruption_start_timestep")
        end = incident.get("corruption_end_timestep")
        warnings: list[str] = []
        errors: list[str] = []

        if start is None and end is None:
            warnings.append(
                "No corruption interval is recorded; exposure cannot be "
                "localized in time"
            )
        if source_environment_version is None:
            warnings.append(
                "No source environment version is recorded for this incident"
            )
        if not artifacts:
            warnings.append("No artifacts are recorded for this run")

        classifications: dict[str, dict[str, Any]] = {}
        for artifact in artifacts:
            status, reason = _classify_initial(
                artifact,
                source_environment_version=source_environment_version,
                start=start,
                end=end,
            )
            classifications[artifact["artifact_id"]] = {
                "artifact_id": artifact["artifact_id"],
                "artifact_type": artifact["artifact_type"],
                "classification": status,
                "reason": reason,
                "timestep": _timestep(artifact),
                "environment_version": artifact.get("environment_version"),
                "propagated": False,
            }

        parents: dict[str, list[str]] = {}
        for artifact in artifacts:
            parent = artifact.get("parent_artifact_id")
            if parent:
                parents.setdefault(artifact["artifact_id"], []).append(parent)
        for link in links:
            parents.setdefault(link["to_artifact_id"], []).append(
                link["from_artifact_id"]
            )

        propagated = False
        for _ in range(max(1, len(artifacts))):
            changed = False
            for artifact_id, parent_ids in parents.items():
                current = classifications.get(artifact_id)
                if current is None or current["classification"] == CONFIRMED:
                    continue
                parent_classes = [
                    classifications[parent]["classification"]
                    for parent in parent_ids
                    if parent in classifications
                ]
                if (
                    CONFIRMED in parent_classes or POTENTIAL in parent_classes
                ) and current["classification"] != POTENTIAL:
                    current["classification"] = POTENTIAL
                    current["reason"] = (
                        "artifact descends from an exposed or potentially "
                        "affected artifact"
                    )
                    current["propagated"] = True
                    propagated = True
                    changed = True
            if not changed:
                break

        if propagated:
            warnings.append(
                "Exposure was propagated through recorded parent/derived links; "
                "this is lineage exposure, not proof of causal damage"
            )

        counts = Counter(
            entry["classification"] for entry in classifications.values()
        )
        if counts[CONFIRMED] > 0:
            impact_status = CONFIRMED
        elif counts[POTENTIAL] > 0:
            impact_status = POTENTIAL
        elif counts[UNKNOWN] > 0:
            impact_status = UNKNOWN
        elif artifacts:
            impact_status = NOT_EXPOSED
        else:
            impact_status = UNKNOWN

        affected = [
            entry
            for entry in classifications.values()
            if entry["classification"] in {CONFIRMED, POTENTIAL}
        ]
        affected_ids = [entry["artifact_id"] for entry in affected]
        affected_artifact_rows = [
            artifact
            for artifact in artifacts
            if artifact["artifact_id"] in set(affected_ids)
        ]
        affected_trajectory_ids = unique_preserving_order(
            artifact["trajectory_id"]
            for artifact in affected_artifact_rows
            if artifact.get("trajectory_id")
        )
        affected_policy_update_ids = unique_preserving_order(
            artifact["policy_update_id"]
            for artifact in affected_artifact_rows
            if artifact.get("policy_update_id")
        )
        affected_checkpoint_ids = unique_preserving_order(
            artifact.get("checkpoint_id") or artifact["artifact_id"]
            for artifact in affected_artifact_rows
            if artifact["artifact_type"] == "checkpoint"
        )

        unknown_count = counts[UNKNOWN]
        if unknown_count > 0:
            impact_score = None
            warnings.append(
                f"{unknown_count} artifact(s) have incomplete lineage; the "
                "impact score is withheld"
            )
        elif artifacts:
            impact_score = round(
                (counts[CONFIRMED] + 0.5 * counts[POTENTIAL]) / len(artifacts),
                4,
            )
        else:
            impact_score = None

        details = {
            "classifications": list(classifications.values()),
            "classification_counts": {
                CONFIRMED: counts[CONFIRMED],
                POTENTIAL: counts[POTENTIAL],
                NOT_EXPOSED: counts[NOT_EXPOSED],
                UNKNOWN: counts[UNKNOWN],
            },
            "score_definition": (
                "Exposure index over recorded artifacts: confirmed=1.0, "
                "potential=0.5. It is not a measure of causal damage."
            ),
            "causal_claim": (
                "Exposure does not establish that performance was degraded "
                "by the fault."
            ),
        }
        evidence_ids = unique_preserving_order(incident.get("evidence_ids", []))

        return {
            "incident_id": incident["incident_id"],
            "run_id": incident["run_id"],
            "impact_status": impact_status,
            "impact_score": impact_score,
            "source_environment_version": source_environment_version,
            "corruption_start_timestep": start,
            "corruption_end_timestep": end,
            "affected_artifact_ids": affected_ids,
            "affected_trajectory_ids": affected_trajectory_ids,
            "affected_policy_update_ids": affected_policy_update_ids,
            "affected_checkpoint_ids": affected_checkpoint_ids,
            "evidence_ids": evidence_ids,
            "warnings": warnings,
            "errors": errors,
            "details": details,
        }

    @staticmethod
    def _same_analysis(latest: dict[str, Any], computed: dict[str, Any]) -> bool:
        keys = (
            "impact_status",
            "impact_score",
            "source_environment_version",
            "corruption_start_timestep",
            "corruption_end_timestep",
            "affected_artifact_ids",
            "affected_trajectory_ids",
            "affected_policy_update_ids",
            "affected_checkpoint_ids",
        )
        return all(latest.get(key) == computed.get(key) for key in keys)

    def analyze_incident_impact(
        self,
        incident_id: str,
        *,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        with self.database.write() as conn:
            incident = load_incident(conn, incident_id)
            if incident is None:
                raise IncidentNotFoundError(
                    "Incident was not found",
                    details={"incident_id": incident_id},
                )
            run = runs_repo.get_run(conn, incident["run_id"])
            if run is None:
                raise RunNotFoundError(
                    "The incident's run is not registered",
                    details={"run_id": incident["run_id"]},
                )
            artifacts = artifacts_repo.list_artifacts_for_run(
                conn, incident["run_id"]
            )
            links = artifacts_repo.list_links_for_run(conn, incident["run_id"])
            computed = self._compute(
                incident=incident, artifacts=artifacts, links=links
            )
            latest = impacts_repo.get_latest_impact_for_incident(conn, incident_id)
            if latest is not None and self._same_analysis(latest, computed):
                return latest
            created = impacts_repo.create_impact(conn, **computed)
            audit_repo.append_audit(
                conn,
                entity_type="impact_analysis",
                entity_id=created["impact_id"],
                action="computed",
                status=created["impact_status"],
                correlation_id=correlation_id,
                details={
                    "incident_id": incident_id,
                    "run_id": incident["run_id"],
                    "impact_score": created["impact_score"],
                },
            )
            return created

    def get_incident_impact(
        self,
        incident_id: str,
        *,
        correlation_id: str | None = None,
    ) -> ImpactAnalysis:
        return ImpactAnalysis.model_validate(
            self.analyze_incident_impact(
                incident_id, correlation_id=correlation_id
            )
        )
