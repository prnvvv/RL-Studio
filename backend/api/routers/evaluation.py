"""Evaluation router for recovery verification."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Any, Dict

from backend.verification.agent.agent_state import VerificationState
from backend.verification.models import VerificationCheckResult, CheckStatus

from backend.evaluation.models import Evaluation, EvaluationCreateRequest

from ..dependencies import Services, get_correlation_id, get_services

router = APIRouter(tags=["evaluation"])


@router.get("/evaluation/results/{evaluation_id}")
async def get_evaluation_results(
    evaluation_id: str,
    state: VerificationState = Depends(),
) -> Dict[str, Any]:
    """Get evaluation results - no hardcoded success."""
    return {
        "evaluation_id": evaluation_id,
        "status": "not_run",
        "recovery_verified": False,
        "note": "Evaluation required for recovery verification",
    }


# Person 4 API endpoints
p4_router = APIRouter(prefix="/api/v1", tags=["evaluation"])


@p4_router.post(
    "/incidents/{incident_id}/evaluations",
    response_model=Evaluation,
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate a recovered policy against healthy and faulty baselines",
)
def create_evaluation(
    incident_id: str,
    payload: EvaluationCreateRequest,
    services: Annotated[Services, Depends(get_services)],
    correlation_id: Annotated[Optional[str], Depends(get_correlation_id)] = None,
) -> Evaluation:
    return services.evaluation.create_evaluation(
        incident_id, payload, correlation_id=correlation_id
    )


@p4_router.get(
    "/incidents/{incident_id}/evaluations/{evaluation_id}",
    response_model=Evaluation,
    summary="Get an evaluation result and acceptance checks",
)
def get_evaluation(
    incident_id: str,
    evaluation_id: str,
    services: Annotated[Services, Depends(get_services)],
) -> Evaluation:
    return services.evaluation.get_evaluation(incident_id, evaluation_id)


router.include_router(p4_router)
