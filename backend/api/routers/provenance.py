"""Provenance router for artifact impact assessment."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from backend.provenance.models import (
    Artifact,
    ImpactAnalysis,
    ProvenanceTrace,
    RunArtifactList,
)

from ..dependencies import Services, get_services

router = APIRouter(tags=["provenance"])

# Person 4 API endpoints
p4_router = APIRouter(prefix="/api/v1", tags=["provenance"])

Identifier2 = Annotated[str, Path(min_length=1, max_length=200)]


@p4_router.get(
    "/runs/{run_id}/provenance",
    response_model=ProvenanceTrace,
    summary="Get a run's provenance trace",
)
def get_run_provenance(
    run_id: Identifier2,
    services: Annotated[Services, Depends(get_services)],
) -> ProvenanceTrace:
    return services.provenance.get_run_provenance(run_id)


@p4_router.get(
    "/runs/{run_id}/artifacts",
    response_model=RunArtifactList,
    summary="List artifacts associated with a run",
)
def list_run_artifacts(
    run_id: Identifier2,
    services: Annotated[Services, Depends(get_services)],
) -> RunArtifactList:
    return services.provenance.list_run_artifacts(run_id)


@p4_router.get(
    "/artifacts/{artifact_id}",
    response_model=Artifact,
    summary="Get artifact metadata and integrity status",
)
def get_artifact(
    artifact_id: Identifier2,
    services: Annotated[Services, Depends(get_services)],
) -> Artifact:
    return services.provenance.get_artifact(artifact_id)


@p4_router.get(
    "/incidents/{incident_id}/impact",
    response_model=ImpactAnalysis,
    summary="Get evidence-backed artifact exposure impact",
)
def get_incident_impact(
    incident_id: Identifier2,
    services: Annotated[Services, Depends(get_services)],
) -> ImpactAnalysis:
    return services.provenance.get_incident_impact(incident_id)


router.include_router(p4_router)
