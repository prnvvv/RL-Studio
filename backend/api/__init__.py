"""API routes for persistence, provenance, recovery, and evaluation."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from backend.verification.agent.agent_state import VerificationState
from backend.verification.tools.tool_registry import execute_check, list_checks
from backend.verification.models import (
    VerificationRequirement,
    VerificationCheckResult,
    CheckStatus,
    RequirementType,
)
from backend.verification.exceptions import GuardrailViolation

router = APIRouter(prefix="/api/v1", tags=["verification"])


@router.get("/verification/status", response_model=Dict[str, CheckStatus])
async def get_verification_status(state: VerificationState = Depends()) -> Dict[str, CheckStatus]:
    """Get current verification status without overriding deterministic results."""
    return {"overall_status": state.overall_status} if state.overall_status else {}


@router.post("/verification/check/{check_id}")
async def run_check(
    check_id: str,
    state: VerificationState = Depends(),
) -> Dict[str, Any]:
    """Run a single verification check without overriding deterministic results."""
    # Use the tool registry to execute the check
    from backend.verification.tools.tool_registry import is_check_registered

    if not is_check_registered(check_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check {check_id} not registered",
        )

    # Execute through registry - this respects deterministic results
    # The registry's execute_check adapts to checker signatures
    result = execute_check(check_id, state)  # simplified for compatibility

    return {
        "check_id": check_id,
        "status": result.status,
        "expected": result.expected,
        "actual": result.actual,
        "details": result.details,
    }


@router.get("/checks/registered")
async def get_registered_checks() -> Dict[str, str]:
    """Get list of registered check IDs."""
    return {"checks": list_checks()} if list_checks() else {}


@router.post("/compatibility/verify")
async def verify_compatibility(
    requirement: VerificationRequirement,
) -> Dict[str, Any]:
    """Verify a requirement without overriding deterministic results.

    This endpoint respects the deterministic verification foundation.
    LLM output must not override FAIL, UNKNOWN, BLOCKED, or PENDING into PASS.
    """
    from backend.verification.agent.decision_engine import aggregate_results

    # Execute the check through the registry
    check_id = requirement.type.value if hasattr(requirement, 'type') else "check_reward"

    # Execute through metric/reward checker
    from backend.verification.tools import metric_checker as mc
    from backend.verification.tools import reward_checker as rc
    from backend.verification.models import RequirementType

    # Use the appropriate checker based on requirement type
    checker_map = {
        RequirementType.reward: lambda: rc.execute_check(
            "c", requirement, observed_reward=getattr(requirement, 'actual', None)
        ),
        RequirementType.termination: lambda: mc.execute_check(
            "c", requirement, metric_values=[getattr(requirement, 'actual', 1.0)]
        ),
    }

    checker = checker_map.get(requirement.type, lambda: {"status": "unknown"})
    result = checker()

    # Aggregate using deterministic engine - LLM cannot upgrade FAIL to PASS
    aggregation = aggregate_results({check_id: result})

    return {
        "requirement_id": requirement.id,
        "requirement_type": requirement.type.value if hasattr(requirement, 'type') else "unknown",
        "check_result": {
            "status": result.status,
            "expected": result.expected,
            "actual": result.actual,
        },
        "aggregated_status": aggregation["overall_status"].value,
        "deterministic_authority": "LLM output must not override deterministic failures",
    }
