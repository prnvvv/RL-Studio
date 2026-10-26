from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Path, status

from backend.evaluation.models import Evaluation, EvaluationCreateRequest

from ..dependencies import Services, get_correlation_id, get_services

router = APIRouter(prefix="/api/v1", tags=["evaluation"])

Identifier = Annotated[str, Path(min_length=1, max_length=200)]
CorrelationId = Annotated[Optional[str], Depends(get_correlation_id)]


@router.post(
    "/incidents/{incident_id}/evaluations",
    response_model=Evaluation,
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate a recovered policy against healthy and faulty baselines",
)
def create_evaluation(
    incident_id: Identifier,
    payload: EvaluationCreateRequest,
    services: Annotated[Services, Depends(get_services)],
    correlation_id: CorrelationId = None,
) -> Evaluation:
    return services.evaluation.create_evaluation(
        incident_id, payload, correlation_id=correlation_id
    )


@router.get(
    "/incidents/{incident_id}/evaluations/{evaluation_id}",
    response_model=Evaluation,
    summary="Get an evaluation result and acceptance checks",
)
def get_evaluation(
    incident_id: Identifier,
    evaluation_id: Identifier,
    services: Annotated[Services, Depends(get_services)],
) -> Evaluation:
    return services.evaluation.get_evaluation(incident_id, evaluation_id)
