"""Provenance router for artifact impact assessment."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, Dict

from backend.verification.agent.agent_state import VerificationState
from backend.verification.models import VerificationCheckResult, CheckStatus
from backend.verification.tools.tool_registry import execute_check, list_checks

from backend.provenance.models import (
    Artifact,
    ImpactAnalysis,
    ProvenanceTrace,
    RunArtifactList,
)

from ..dependencies import Services, get_services

router = APIRouter(tags=["provenance"])


@router.get("/provenance/artifact-impact/{artifact_id}")
async def get_artifact_impact(
    artifact_id: str,
    state: VerificationState = Depends(),
) -> Dict[str, Any]:
    """Get artifact impact assessment."""
    # Use deterministic evidence; no fabricating impact status
    impact: Dict[str, Any] = {
        "artifact_id": artifact_id,
        "impact_status": "unknown",
        "evidence_authority": "Deterministic records; no fabricating impact status",
    }

    if state.overall_status == CheckStatus.PASS:
        impact["impact_status"] = "exposed_potentially_affected_unknown"
    elif state.overall_status == CheckStatus.FAIL:
        impact["impact_status"] = "exposed_potentially_affected_unknown"
    else:
        impact["impact_status"] = "unknown"

    return impact


@router.get("/provenance/lineage/{run_id}")
async def get_lineage(
    run_id: str,
    state: VerificationState = Depends(),
) -> Dict[str, Any]:
    """Get artifact lineage for a run."""
    lineage: Dict[str, Any] = {
        "run_id": run_id,
        "lineage_authority": "Deterministic records with stable IDs; no inventing relationships",
    }

    if state.overall_status == CheckStatus.PASS:
        lineage["lineage_status"] = "complete_verified_lineage"
    elif state.overall_status == CheckStatus.FAIL:
        lineage["lineage_status"] = "incomplete_verified_lineage"
    else:
        lineage["lineage_status"] = "unknown_insufficient_evidence"

    return lineage


# Person 4 API endpoints
p4_router = APIRouter(prefix="/api/v1", tags=["provenance"])

Identifier = Annotated[str, Depends(lambda x: x.path_params.get("run_id") or x.path_params.get("artifact_id") or x.path_params.get("incident_id"))]  # fallback not needed


from fastapi import Path

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
    summary="List a run's registered artifacts",
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
