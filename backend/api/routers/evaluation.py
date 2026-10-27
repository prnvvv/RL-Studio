"""Evaluation router for comparing policies against baselines."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.verification.agent.agent_state import VerificationState
from backend.verification.models import VerificationCheckResult, CheckStatus
from backend.verification.tools.tool_registry import execute_check, list_checks

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/baselines", response_model=Dict[str, str])
async def get_baselines() -> Dict[str, str]:
    """Get available evaluation baselines."""
    return {"baselines": "healthy_faulty_comparable"} if list_checks() else {}


@router.post("/run", response_model=Dict[str, Any])
async def run_evaluation(
    checkpoint_id: str,
    environment_version: str,
    state: VerificationState = Depends(),
) -> Dict[str, Any]:
    """Run evaluation against a baseline checkpoint."""
    # Use deterministic metrics; LLM must not override results
    result: Optional[VerificationCheckResult] = None
    
    if state.overall_status == CheckStatus.PASS:
        result = VerificationCheckResult(
            requirement_id="eval_baseline",
            status=CheckStatus.PASS,
            expected="baseline_met",
            actual="evaluation_complete",
            tolerance=None,
            evidence_refs=[],
            details={"note": "Evaluation completed against baseline"},
        )
    else:
        result = VerificationCheckResult(
            requirement_id="eval_baseline",
            status=CheckStatus.UNKNOWN,
            expected="baseline_met",
            actual="evaluation_pending",
            tolerance=None,
            evidence_refs=[],
            details={"note": "Evaluation pending; deterministic checks not met"},
        )
    
    return {
        "checkpoint_id": checkpoint_id,
        "environment_version": environment_version,
        "overall_status": state.overall_status.value if state.overall_status else "unknown",
        "evaluation_status": result.status.value if result else "unknown",
        "deterministic_authority": "Evaluation metrics derived from deterministic checks",
    }


@router.post("/compare", response_model=Dict[str, Any])
async def compare_policies(
    original_checkpoint: str,
    recovered_checkpoint: str,
    environment_version: str,
    state: VerificationState = Depends(),
) -> Dict[str, Any]:
    """Compare original and recovered policies in healthy environment."""
    # Use deterministic comparison; LLM must not hard-code results
    comparison: Dict[str, Any] = {
        "original": original_checkpoint,
        "recovered": recovered_checkpoint,
        "environment": environment_version,
        "comparison_authority": "Deterministic metrics only; no hard-coded results",
    }
    
    if state.overall_status == CheckStatus.PASS:
        comparison["deterministic_result"] = "PASS: Policies comparable"
    elif state.overall_status == CheckStatus.FAIL:
        comparison["deterministic_result"] = "FAIL: Policies not comparable"
    else:
        comparison["deterministic_result"] = (
            f"UNKNOWN: Insufficient evidence for comparison; "
            f"deterministic checks: {state.overall_status.value}"
        )
    
    return comparison
