from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RecoveryEligibility(str, Enum):
    eligible = "eligible"
    ineligible = "ineligible"
    needs_review = "needs_review"
    unknown = "unknown"


class RecoveryStrategy(str, Enum):
    restore_checkpoint = "restore_checkpoint"
    correct_environment_config = "correct_environment_config"
    discard_pending_rollouts = "discard_pending_rollouts"
    continue_with_fresh_experience = "continue_with_fresh_experience"
    evaluate_only = "evaluate_only"


class RecoveryStatus(str, Enum):
    proposed = "proposed"
    approved = "approved"
    executing = "executing"
    completed = "completed"
    failed = "failed"
    blocked = "blocked"
    cancelled = "cancelled"
    evaluated = "evaluated"


class CheckOutcome(str, Enum):
    pass_ = "pass"
    fail = "fail"
    unknown = "unknown"
    blocked = "blocked"
    skipped = "skipped"


class CompatibilityCheck(BaseModel):
    name: str
    outcome: CheckOutcome
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)


class Approval(BaseModel):
    approved: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None
    note: str | None = None


class RecoveryAssessmentRequest(BaseModel):
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.restore_checkpoint
    source_checkpoint_id: str | None = None
    target_environment_version: str | None = None
    target_agent_config_fingerprint: str | None = None
    recovery_reason: str | None = None
    discard_pending_rollouts: bool = True
    collect_fresh_experience: bool = True
    evidence_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class RecoveryAssessment(BaseModel):
    recovery_assessment_id: str
    incident_id: str
    recovery_eligibility: RecoveryEligibility
    recovery_strategy: RecoveryStrategy
    recovery_reason: str | None = None
    source_checkpoint_id: str | None = None
    target_environment_version: str | None = None
    target_agent_config_fingerprint: str | None = None
    compatibility: list[CompatibilityCheck] = Field(default_factory=list)
    lineage_gaps: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RecoveryCreateRequest(BaseModel):
    assessment_id: str | None = None
    recovery_strategy: RecoveryStrategy | None = None
    source_checkpoint_id: str | None = None
    target_environment_version: str | None = None
    target_agent_config_fingerprint: str | None = None
    recovery_reason: str | None = None
    execute: bool = False
    approval: Approval | None = None
    discard_pending_rollouts: bool = True
    collect_fresh_experience: bool = True
    evidence_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class RecoveryAction(BaseModel):
    action: str
    status: str
    detail: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class Recovery(BaseModel):
    recovery_id: str
    incident_id: str
    assessment_id: str | None = None
    recovery_status: RecoveryStatus
    recovery_strategy: RecoveryStrategy
    recovery_reason: str | None = None
    source_checkpoint_id: str | None = None
    recovery_artifact_id: str | None = None
    recovered_checkpoint_id: str | None = None
    target_environment_version: str | None = None
    target_agent_config_fingerprint: str | None = None
    recovery_started_at: datetime | None = None
    recovery_completed_at: datetime | None = None
    proposed_actions: list[RecoveryAction] = Field(default_factory=list)
    executed_actions: list[RecoveryAction] = Field(default_factory=list)
    preflight: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
