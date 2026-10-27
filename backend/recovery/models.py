"""Recovery logic: plan, validate, execute, evaluate (AGENTS.md §7.5, §13)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from shared.schemas import (
    Incident,
    IncidentStatus,
    Recovery,
    RecoveryAction,
    RecoveryStatus,
    Evaluation,
    EvaluationStatus,
    MetricResult,
    SourceComponent,
)
from backend.provenance.models import ArtifactFingerprint, LineageRecord, ExposureStatus


class RecoveryPlanStatus(str, Enum):
    PLANNED = "planned"
    VALIDATING = "validating"
    APPROVED = "approved"
    EXECUTING = "executing"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class CompatibilityResult(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class RecoveryPlan(BaseModel):
    """A recovery plan with proposed actions and compatibility checks."""

    plan_id: str = Field(default_factory=lambda: "rec_" + Incident.__fields__["incident_id"].default_factory.__name__() if hasattr(Incident.__fields__["incident_id"].default_factory, '__call__') else "rec_placeholder")
    incident_id: str
    proposed_actions: list[RecoveryAction] = Field(default_factory=list)
    executed_actions: list[RecoveryAction] = Field(default_factory=list)
    source_checkpoint_id: Optional[str] = None
    target_checkpoint_id: Optional[str] = None
    environment_fingerprint: Optional[str] = None
    agent_config_fingerprint: Optional[str] = None
    compatibility_checks: list[Dict[str, Any]] = Field(default_factory=list)
    approval_state: str = "pending"
    status: RecoveryPlanStatus = RecoveryPlanStatus.PLANNED
    failure_reason: Optional[str] = None
    evaluation_id: Optional[str] = None
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=lambda: utc_now().isoformat())

    model_config = {"populate_by_name": True, "extra": "forbid"}


def utc_now() -> str:
    """ISO-8601 UTC timestamp."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()