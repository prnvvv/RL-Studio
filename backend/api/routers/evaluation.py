"""Evaluation router for recovery verification."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field

from backend.evaluation.models import AcceptanceCriteria, Evaluation, EvaluationCreateRequest
from backend.evaluation.rollout import DEFAULT_BASE_SEED, MAX_EPISODES
from backend.verification.agent.agent_state import VerificationState

from ..dependencies import Services, get_correlation_id, get_services

router = APIRouter(tags=["evaluation"])


@router.get("/evaluation/results/{evaluation_id}")
async def get_evaluation_results(
    evaluation_id: str,
    state: Annotated[VerificationState, Depends()],
) -> dict[str, Any]:
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
    correlation_id: Annotated[str | None, Depends(get_correlation_id)] = None,
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


@p4_router.get(
    "/incidents/{incident_id}/evaluations",
    summary="List an incident's evaluations (run-level rollouts and recovery acceptance records)",
)
def list_incident_evaluations(
    incident_id: str,
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    services.provenance.get_incident(incident_id)  # 404 for an unknown incident
    items = services.run_evaluation.list_for_incident(incident_id)
    return {"incident_id": incident_id, "count": len(items), "evaluations": items}


class RolloutEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: A checkpoint (artifact or checkpoint id) of this run; defaults to the run's latest saved policy.
    checkpoint_id: str | None = Field(default=None, max_length=128)
    episodes: int = Field(default=20, ge=1, le=MAX_EPISODES)
    base_seed: int = Field(default=DEFAULT_BASE_SEED, ge=0, le=2**31 - 1)
    #: An earlier evaluation in the same project to compare against. Never inferred.
    baseline_evaluation_id: str | None = Field(default=None, max_length=128)
    minimum_mean_reward: float | None = None
    minimum_success_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    maximum_timeout_rate: float | None = Field(default=None, ge=0.0, le=1.0)


@p4_router.post(
    "/runs/{run_id}/evaluations",
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate a run's saved policy by rolling it out in its own environment",
)
def evaluate_run(
    run_id: str,
    payload: RolloutEvaluationRequest,
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    criteria = {k: v for k, v in payload.model_dump(include={"minimum_mean_reward", "minimum_success_rate", "maximum_timeout_rate"}).items() if v is not None}
    return services.run_evaluation.evaluate(
        run_id, checkpoint_id=payload.checkpoint_id, episodes=payload.episodes, base_seed=payload.base_seed,
        baseline_evaluation_id=payload.baseline_evaluation_id, criteria=criteria or None,
    )


@p4_router.get("/runs/{run_id}/evaluations", summary="List a run's policy evaluations, newest first")
def list_run_evaluations(run_id: str, services: Annotated[Services, Depends(get_services)]) -> dict[str, Any]:
    items = services.run_evaluation.list_for_run(run_id)
    return {"run_id": run_id, "count": len(items), "evaluations": items}


@p4_router.get("/runs/{run_id}/evaluations/{run_evaluation_id}", summary="Get one run-level evaluation with its episodes")
def get_run_evaluation(run_id: str, run_evaluation_id: str, services: Annotated[Services, Depends(get_services)]) -> dict[str, Any]:
    return services.run_evaluation.get(run_id, run_evaluation_id)


class RecoveryEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episodes: int = Field(default=20, ge=1, le=MAX_EPISODES)
    base_seed: int = Field(default=DEFAULT_BASE_SEED, ge=0, le=2**31 - 1)
    acceptance_criteria: AcceptanceCriteria = Field(default_factory=AcceptanceCriteria)


@p4_router.post(
    "/incidents/{incident_id}/recoveries/{recovery_id}/evaluate",
    status_code=status.HTTP_201_CREATED,
    summary="Evaluate the policy a recovery produced (rollouts + acceptance record)",
)
def evaluate_recovery(
    incident_id: str,
    recovery_id: str,
    payload: RecoveryEvaluationRequest,
    services: Annotated[Services, Depends(get_services)],
    correlation_id: Annotated[str | None, Depends(get_correlation_id)] = None,
) -> dict[str, Any]:
    return services.run_evaluation.evaluate_recovery(
        incident_id, recovery_id, episodes=payload.episodes, base_seed=payload.base_seed,
        criteria=payload.acceptance_criteria, correlation_id=correlation_id,
    )


router.include_router(p4_router)