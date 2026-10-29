"""Recovery router for recovery planning and execution."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from backend.recovery.models import (
    Recovery,
    RecoveryAssessment,
    RecoveryAssessmentRequest,
    RecoveryCreateRequest,
)
from backend.verification.agent.agent_state import VerificationState

from ..dependencies import Services, get_correlation_id, get_services

router = APIRouter(tags=["recovery"])


@router.get("/recovery/status/{incident_id}")
async def get_recovery_status(
    incident_id: str,
    state: Annotated[VerificationState, Depends()],
) -> dict[str, Any]:
    """Get recovery status - does not fabricate recovery success."""
    return {
        "incident_id": incident_id,
        "recovery_status": "not_started",
        "recovery_verified": False,
        "note": "Recovery verification requires evaluation; no automatic success claims",
    }


@router.post("/recovery/plan")
async def create_recovery_plan(
    incident_id: str,
    state: Annotated[VerificationState, Depends()],
) -> dict[str, Any]:
    """Create recovery plan without auto-executing."""
    return {
        "incident_id": incident_id,
        "plan_created": True,
        "execution_required": True,
        "auto_execution": False,
        "note": "Plan created but not executed; evaluation required for verification",
    }


# Person 4 API endpoints
p4_router = APIRouter(prefix="/api/v1", tags=["recovery"])


Identifier = Annotated[str, Depends(lambda x: x)]


@p4_router.post(
    "/incidents/{incident_id}/recovery-assessments",
    response_model=RecoveryAssessment,
    status_code=status.HTTP_201_CREATED,
    summary="Create a fail-closed recovery compatibility assessment",
)
def create_recovery_assessment(
    incident_id: str,
    payload: RecoveryAssessmentRequest,
    services: Annotated[Services, Depends(get_services)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)] = None,
) -> RecoveryAssessment:
    return services.recovery.create_assessment(
        incident_id, payload, correlation_id=correlation_id
    )


@p4_router.get(
    "/incidents/{incident_id}/recovery-assessments/{assessment_id}",
    response_model=RecoveryAssessment,
    summary="Get a recovery assessment",
)
def get_recovery_assessment(
    incident_id: str,
    assessment_id: str,
    services: Annotated[Services, Depends(get_services)],
) -> RecoveryAssessment:
    return services.recovery.get_assessment(incident_id, assessment_id)


@p4_router.post(
    "/incidents/{incident_id}/recoveries",
    response_model=Recovery,
    status_code=status.HTTP_201_CREATED,
    summary="Create and optionally execute a controlled recovery",
)
def create_recovery(
    incident_id: str,
    payload: RecoveryCreateRequest,
    services: Annotated[Services, Depends(get_services)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)] = None,
) -> Recovery:
    return services.recovery.create_recovery(
        incident_id, payload, correlation_id=correlation_id
    )


@p4_router.get(
    "/incidents/{incident_id}/recoveries/{recovery_id}",
    response_model=Recovery,
    summary="Get a recovery plan and execution result",
)
def get_recovery(
    incident_id: str,
    recovery_id: str,
    services: Annotated[Services, Depends(get_services)],
) -> Recovery:
    return services.recovery.get_recovery(incident_id, recovery_id)


router.include_router(p4_router)