"""Schemas for the model's advisory output (root-cause analysis and recovery recommendations).

These validate what Muse Wonder *proposes*. Nothing here is a verdict: ``grounding.py`` then checks every cited
evidence reference against the persisted records before anything is stored or shown, and no model output can raise
a hypothesis to a confirmed root cause or authorise an action.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Component = Literal["environment", "agent", "configuration", "training_process", "data", "verification", "unknown"]

RecoveryActionName = Literal[
    "rescore_experiences",
    "discard_trajectories",
    "regenerate_experiences",
    "restore_checkpoint",
    "resume_with_corrected_config",
    "restart_training",
    "evaluate_only",
    "no_action",
]

KIND_ROOT_CAUSE = "root_cause"
KIND_RECOVERY_PLAN = "recovery_plan"


class _Loose(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ObservedFact(_Loose):
    statement: str = Field(max_length=500)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class Hypothesis(_Loose):
    component: Component = "unknown"
    description: str = Field(max_length=600)
    supporting_evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    contradicting_evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    confidence: float | None = Field(default=None, ge=0, le=1)
    uncertainty: str = Field(default="", max_length=600)


class RootCauseAnalysis(_Loose):
    summary: str = Field(default="", max_length=1000)
    observed_facts: list[ObservedFact] = Field(default_factory=list, max_length=20)
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=8)
    missing_evidence: list[str] = Field(default_factory=list, max_length=20)
    recommended_investigation: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)


class RecoveryOption(_Loose):
    action: RecoveryActionName
    reason: str = Field(max_length=600)
    supporting_evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    target_checkpoint_id: str | None = Field(default=None, max_length=200)
    expected_impact: str = Field(default="", max_length=600)
    risks: list[str] = Field(default_factory=list, max_length=10)
    preconditions: list[str] = Field(default_factory=list, max_length=10)
    #: advisory only: ``grounding.py`` forces this to true for every state-changing action
    requires_user_authorization: bool = True


class RecoveryPlan(_Loose):
    summary: str = Field(default="", max_length=1000)
    options: list[RecoveryOption] = Field(default_factory=list, max_length=6)
    not_recommended: list[str] = Field(default_factory=list, max_length=10)
    missing_evidence: list[str] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=20)
