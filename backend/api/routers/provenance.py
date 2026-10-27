"""Provenance router for artifact impact assessment."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.verification.agent.agent_state import VerificationState
from backend.verification.models import VerificationCheckResult, CheckStatus
from backend.verification.tools.tool_registry import execute_check, list_checks

router = APIRouter(prefix="/provenance", tags=["provenance"])


@router.get("/artifact-impact/{artifact_id}")
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


@router.get("/lineage/{run_id}")
async def get_lineage(
    run_id: str,
    state: VerificationState = Depends(),
) -> Dict[str, Any]:
    """Get artifact lineage for a run."""
    # Use deterministic lineage; no inventing artifact relationships
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
