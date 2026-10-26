from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Path, status

from backend.recovery.models import (
    Recovery,
    RecoveryAssessment,
    RecoveryAssessmentRequest,
    RecoveryCreateRequest,
)

from ..dependencies import Services, get_correlation_id, get_services

router = APIRouter(prefix="/api/v1", tags=["recovery"])

Identifier = Annotated[str, Path(min_length=1, max_length=200)]
CorrelationId = Annotated[Optional[str], Depends(get_correlation_id)]


@router.post(
    "/incidents/{incident_id}/recovery-assessments",
    response_model=RecoveryAssessment,
    status_code=status.HTTP_201_CREATED,
    summary="Create a fail-closed recovery compatibility assessment",
)
def create_recovery_assessment(
    incident_id: Identifier,
    payload: RecoveryAssessmentRequest,
    services: Annotated[Services, Depends(get_services)],
    correlation_id: CorrelationId = None,
) -> RecoveryAssessment:
    return services.recovery.create_assessment(
        incident_id, payload, correlation_id=correlation_id
    )


@router.get(
    "/incidents/{incident_id}/recovery-assessments/{assessment_id}",
    response_model=RecoveryAssessment,
    summary="Get a recovery assessment",
)
def get_recovery_assessment(
    incident_id: Identifier,
    assessment_id: Identifier,
    services: Annotated[Services, Depends(get_services)],
) -> RecoveryAssessment:
    return services.recovery.get_assessment(incident_id, assessment_id)


@router.post(
    "/incidents/{incident_id}/recoveries",
    response_model=Recovery,
    status_code=status.HTTP_201_CREATED,
    summary="Create and optionally execute a controlled recovery",
)
def create_recovery(
    incident_id: Identifier,
    payload: RecoveryCreateRequest,
    services: Annotated[Services, Depends(get_services)],
    correlation_id: CorrelationId = None,
) -> Recovery:
    return services.recovery.create_recovery(
        incident_id, payload, correlation_id=correlation_id
    )


@router.get(
    "/incidents/{incident_id}/recoveries/{recovery_id}",
    response_model=Recovery,
    summary="Get a recovery plan and execution result",
)
def get_recovery(
    incident_id: Identifier,
    recovery_id: Identifier,
    services: Annotated[Services, Depends(get_services)],
) -> Recovery:
    return services.recovery.get_recovery(incident_id, recovery_id)
