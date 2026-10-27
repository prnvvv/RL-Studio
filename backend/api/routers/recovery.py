"""Recovery router for validated recovery actions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.verification.agent.agent_state import VerificationState
from backend.verification.models import VerificationCheckResult, CheckStatus
from backend.verification.tools.tool_registry import execute_check, list_checks

router = APIRouter(prefix="/recovery", tags=["recovery"])


@router.post("/validate/{checkpoint_id}")
async def validate_recovery(
    checkpoint_id: str,
    state: VerificationState = Depends(),
) -> Dict[str, Any]:
    """Validate a recovery action before execution."""
    # Recovery must use validated evidence; not successful without verification
    validation: Dict[str, Any] = {
        "checkpoint_id": checkpoint_id,
        "validation_status": "blocked",
        "authority": "Recovery not successful until defined evaluation completes",
    }
    
    if state.overall_status == CheckStatus.PASS:
        validation["validation_status"] = "validated_pending_evaluation"
    elif state.overall_status == CheckStatus.FAIL:
        validation["validation_status"] = "blocked_failure_detected"
    elif state.overall_status == CheckStatus.UNKNOWN:
        validation["validation_status"] = "blocked_insufficient_evidence"
    else:
        validation["validation_status"] = "blocked_recovery_invalid_status"
    
    return validation


@router.post("/execute/{checkpoint_id}")
async def execute_recovery(
    checkpoint_id: str,
    state: VerificationState = Depends(),
) -> Dict[str, Any]:
    """Execute a recovery action (only after validation)."""
    # Recovery is not successful until evaluation completes
    execution: Dict[str, Any] = {
        "checkpoint_id": checkpoint_id,
        "execution_status": "blocked",
        "authority": "Recovery not successful until evaluation completes and meets acceptance criteria",
    }
    
    if state.overall_status == CheckStatus.PASS:
        execution["execution_status"] = "evaluation_pending"
    else:
        execution["execution_status"] = "blocked_cannot_execute_before_validation"
    
    return execution
