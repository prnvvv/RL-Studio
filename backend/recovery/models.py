from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

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
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    note: Optional[str] = None


class RecoveryAssessmentRequest(BaseModel):
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.restore_checkpoint
    source_checkpoint_id: Optional[str] = None
    target_environment_version: Optional[str] = None
    target_agent_config_fingerprint: Optional[str] = None
    recovery_reason: Optional[str] = None
    discard_pending_rollouts: bool = True
    collect_fresh_experience: bool = True
    evidence_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None


class RecoveryAssessment(BaseModel):
    recovery_assessment_id: str
    incident_id: str
    recovery_eligibility: RecoveryEligibility
    recovery_strategy: RecoveryStrategy
    recovery_reason: Optional[str] = None
    source_checkpoint_id: Optional[str] = None
    target_environment_version: Optional[str] = None
    target_agent_config_fingerprint: Optional[str] = None
    compatibility: list[CompatibilityCheck] = Field(default_factory=list)
    lineage_gaps: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RecoveryCreateRequest(BaseModel):
    assessment_id: Optional[str] = None
    recovery_strategy: Optional[RecoveryStrategy] = None
    source_checkpoint_id: Optional[str] = None
    target_environment_version: Optional[str] = None
    target_agent_config_fingerprint: Optional[str] = None
    recovery_reason: Optional[str] = None
    execute: bool = False
    approval: Optional[Approval] = None
    discard_pending_rollouts: bool = True
    collect_fresh_experience: bool = True
    evidence_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None


class RecoveryAction(BaseModel):
    action: str
    status: str
    detail: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class Recovery(BaseModel):
    recovery_id: str
    incident_id: str
    assessment_id: Optional[str] = None
    recovery_status: RecoveryStatus
    recovery_strategy: RecoveryStrategy
    recovery_reason: Optional[str] = None
    source_checkpoint_id: Optional[str] = None
    recovery_artifact_id: Optional[str] = None
    recovered_checkpoint_id: Optional[str] = None
    target_environment_version: Optional[str] = None
    target_agent_config_fingerprint: Optional[str] = None
    recovery_started_at: Optional[datetime] = None
    recovery_completed_at: Optional[datetime] = None
    proposed_actions: list[RecoveryAction] = Field(default_factory=list)
    executed_actions: list[RecoveryAction] = Field(default_factory=list)
    preflight: dict[str, Any] = Field(default_factory=dict)
    failure_reason: Optional[str] = None
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
