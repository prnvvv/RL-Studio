from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class EvaluationStatus(str, Enum):
    passed = "passed"
    failed = "failed"
    inconclusive = "inconclusive"
    not_run = "not_run"
    blocked = "blocked"


class EpisodeEvaluation(BaseModel):
    episode_id: Optional[str] = None
    seed: int = Field(ge=0)
    reward: float
    episode_length: int = Field(ge=0)
    success: bool
    collision: bool = False
    timed_out: bool = False
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AcceptanceCriteria(BaseModel):
    minimum_recovered_success_rate: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    minimum_success_rate_improvement_vs_faulty: Optional[float] = Field(
        default=None, ge=-1.0, le=1.0
    )
    maximum_success_rate_regression_vs_healthy: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    minimum_mean_reward_improvement_vs_faulty: Optional[float] = None
    maximum_mean_reward_regression_vs_healthy: Optional[float] = None
    maximum_collision_rate: Optional[float] = Field(
        default=None, ge=0.0, le=1.0
    )
    maximum_timeout_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    minimum_valid_episodes_per_group: Optional[int] = Field(
        default=None, ge=1
    )
    require_no_episode_errors: bool = False


class EvaluationCreateRequest(BaseModel):
    recovery_id: Optional[str] = None
    baseline_run_id: str
    baseline_checkpoint_id: str
    recovered_run_id: str
    recovered_checkpoint_id: str
    faulty_run_id: Optional[str] = None
    faulty_checkpoint_id: Optional[str] = None
    evaluation_environment_version: str
    environment_healthy: bool
    baseline_episodes: list[EpisodeEvaluation]
    recovered_episodes: list[EpisodeEvaluation]
    faulty_episodes: list[EpisodeEvaluation] = Field(default_factory=list)
    acceptance_criteria: AcceptanceCriteria = Field(
        default_factory=AcceptanceCriteria
    )
    evidence_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None

    @model_validator(mode="after")
    def _validate_faulty_identity(self) -> "EvaluationCreateRequest":
        if self.faulty_episodes and (
            not self.faulty_run_id or not self.faulty_checkpoint_id
        ):
            raise ValueError(
                "faulty_run_id and faulty_checkpoint_id are required when "
                "faulty_episodes are supplied"
            )
        if self.faulty_checkpoint_id and not self.faulty_run_id:
            raise ValueError(
                "faulty_run_id is required when faulty_checkpoint_id is supplied"
            )
        return self


class Evaluation(BaseModel):
    evaluation_id: str
    incident_id: str
    recovery_id: Optional[str] = None
    baseline_run_id: Optional[str] = None
    recovered_run_id: Optional[str] = None
    evaluation_status: EvaluationStatus
    evaluation_environment_version: Optional[str] = None
    baseline_mean_reward: Optional[float] = None
    recovered_mean_reward: Optional[float] = None
    baseline_success_rate: Optional[float] = None
    recovered_success_rate: Optional[float] = None
    baseline_episode_length: Optional[float] = None
    recovered_episode_length: Optional[float] = None
    reward_improvement: Optional[float] = None
    success_rate_improvement: Optional[float] = None
    evaluation_metrics: dict[str, Any] = Field(default_factory=dict)
    comparison_results: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: dict[str, Any] = Field(default_factory=dict)
    recovery_verification_status: EvaluationStatus
    recovery_verified: bool = False
    episode_count: Optional[int] = None
    seeds: list[int] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    completed_at: Optional[datetime] = None
