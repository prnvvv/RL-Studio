from __future__ import annotations

from typing import Any, Optional

from backend.database.connection import Database

from .impact import ImpactAnalyzer
from .models import (
    Artifact,
    ArtifactRegistration,
    ImpactAnalysis,
    Incident,
    IncidentRegistration,
    ProvenanceTrace,
    Run,
    RunArtifactList,
    RunRegistration,
)
from .registry import ArtifactRegistry, load_incident
from .trace import ProvenanceTracer


class ProvenanceService:
    """Facade used by the API layer and by Person 2/Person 3 handoff code."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.registry = ArtifactRegistry(database)
        self.tracer = ProvenanceTracer(database)
        self.impact = ImpactAnalyzer(database)

    def register_run(
        self, request: RunRegistration, *, correlation_id: Optional[str] = None
    ) -> Run:
        return Run.model_validate(
            self.registry.register_run(request, correlation_id=correlation_id)
        )

    def register_artifact(
        self,
        request: ArtifactRegistration,
        *,
        correlation_id: Optional[str] = None,
    ) -> Artifact:
        return Artifact.model_validate(
            self.registry.register_artifact(request, correlation_id=correlation_id)
        )

    def register_incident(
        self,
        request: IncidentRegistration,
        *,
        correlation_id: Optional[str] = None,
    ) -> Incident:
        return Incident.model_validate(
            self.registry.register_incident(request, correlation_id=correlation_id)
        )

    def get_incident(self, incident_id: str) -> Incident:
        from .exceptions import IncidentNotFoundError

        with self.database.read() as conn:
            incident = load_incident(conn, incident_id)
        if incident is None:
            raise IncidentNotFoundError(
                "Incident was not found", details={"incident_id": incident_id}
            )
        return Incident.model_validate(incident)

    def get_run_provenance(
        self, run_id: str, *, correlation_id: Optional[str] = None
    ) -> ProvenanceTrace:
        return self.tracer.get_run_provenance(run_id)

    def list_run_artifacts(
        self, run_id: str, *, correlation_id: Optional[str] = None
    ) -> RunArtifactList:
        artifacts = [
            Artifact.model_validate(row)
            for row in self.tracer.list_run_artifacts(run_id)
        ]
        return RunArtifactList(
            run_id=run_id, count=len(artifacts), artifacts=artifacts
        )

    def get_artifact(
        self, artifact_id: str, *, correlation_id: Optional[str] = None
    ) -> Artifact:
        return Artifact.model_validate(self.tracer.get_artifact(artifact_id))

    def get_incident_impact(
        self, incident_id: str, *, correlation_id: Optional[str] = None
    ) -> ImpactAnalysis:
        return self.impact.get_incident_impact(
            incident_id, correlation_id=correlation_id
        )
