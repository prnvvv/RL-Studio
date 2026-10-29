"""Canonical incident, recovery, and evaluation contracts (AGENTS.md §7.4, §7.5).

These models deliberately keep three things distinct so the UI and audit trail
can report them honestly:

- *detection* status (was a contract violated?)
- *diagnosis* status (what is the likely cause? "confirmed"/"probable"/"unresolved")
- *recovery/evaluation* status (did a fix pass evaluation?)

A low reward, a temporal overlap, or an anomaly score is never, by itself,
treated as proof of a fault or a successful recovery.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .base import SCHEMA_VERSION, new_uuid


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"
    FALSE_POSITIVE = "false_positive"


class ViolationSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RootCauseStatus(str, Enum):
    """Distinction required by §7.4: detection != diagnosis != proof."""

    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    UNRESOLVED = "unresolved"


class Incident(BaseModel):
    """A detected contract violation with evidence, separate from diagnosis."""

    incident_id: str = Field(default_factory=new_uuid)
    schema_version: str = Field(default=SCHEMA_VERSION)
    run_id: str
    requirement_id: Optional[str] = Field(default=None, description="Violated requirement ID.")
    environment_version: Optional[str] = Field(default=None)
    environment_id: Optional[str] = Field(default=None)
    violation_type: str = Field(description="Stable violation category, e.g. 'reward_scale_mismatch'.")
    severity: ViolationSeverity = Field(default=ViolationSeverity.MEDIUM)
    status: IncidentStatus = Field(default=IncidentStatus.OPEN)
    detection_status: str = Field(
        default="confirmed",
        description="Whether the detection itself is 'confirmed', 'suspected', or 'unresolved'.",
    )
    diagnosis_status: RootCauseStatus = Field(
        default=RootCauseStatus.UNRESOLVED,
        description="Separate from detection: is the root cause established?",
    )
    evidence_event_ids: List[str] = Field(
        default_factory=list, description="IDs of ExecutionEvent records proving the violation."
    )
    evidence_refs: List[str] = Field(default_factory=list)
    detector_id: Optional[str] = None
    detector_version: Optional[str] = None
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None
    extensions: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class RecoveryAction(str, Enum):
    """Allow-listed recovery actions (recovery actions must be allow-listed, §11)."""

    RESTORE_CHECKPOINT = "restore_checkpoint"
    COLLECT_FRESH_EXPERIENCE = "collect_fresh_experience"
    RESUME_TRAINING = "resume_training"


class RecoveryStatus(str, Enum):
    PLANNED = "planned"
    VALIDATING = "validating"
    APPROVED = "approved"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


class CompatibilityCheck(BaseModel):
    """A single deterministic compatibility result before a restore (§13)."""

    name: str
    passed: bool
    detail: Optional[str] = None


class Recovery(BaseModel):
    """Recovery record. Proposed and executed actions are kept separate (§7.5)."""

    recovery_id: str = Field(default_factory=new_uuid)
    schema_version: str = Field(default=SCHEMA_VERSION)
    incident_id: str
    proposed_actions: List[RecoveryAction] = Field(default_factory=list)
    executed_actions: List[RecoveryAction] = Field(
        default_factory=list,
        description="Actions that were actually run, distinct from proposed.",
    )
    source_checkpoint_id: Optional[str] = None
    target_checkpoint_id: Optional[str] = Field(
        default=None, description="Checkpoint chosen as the recovery target."
    )
    environment_fingerprint: Optional[str] = None
    agent_config_fingerprint: Optional[str] = None
    compatibility_checks: List[CompatibilityCheck] = Field(default_factory=list)
    approval_state: str = Field(default="pending", description="'pending' | 'approved' | 'rejected'.")
    status: RecoveryStatus = Field(default=RecoveryStatus.PLANNED)
    failure_reason: Optional[str] = Field(
        default=None, description="Sanitized reason when status is FAILED/BLOCKED."
    )
    evaluation_id: Optional[str] = Field(
        default=None, description="Evaluation that must pass to mark SUCCEEDED."
    )
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    extensions: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class EvaluationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class MetricResult(BaseModel):
    """A measured metric with its mean, variability, and explicit denominator."""

    metric_name: str
    value: float
    unit: Optional[str] = None
    mean: Optional[float] = None
    stdev: Optional[float] = Field(default=None, description="Standard deviation across seeds/episodes.")
    ci_low: Optional[float] = Field(default=None, description="Lower confidence-interval bound.")
    ci_high: Optional[float] = Field(default=None, description="Upper confidence-interval bound.")
    sample_count: int = Field(default=0, description="Number of samples (episodes/seeds).")
    note: Optional[str] = None


class Evaluation(BaseModel):
    """Post-recovery evaluation against defined baselines (§7.5, §14)."""

    evaluation_id: str = Field(default_factory=new_uuid)
    schema_version: str = Field(default=SCHEMA_VERSION)
    recovery_id: Optional[str] = None
    run_id: Optional[str] = None
    environment_version: str = Field(description="Healthy evaluation environment version.")
    policy_fingerprint: Optional[str] = Field(default=None)
    n_episodes: int = Field(description="Number of evaluation episodes.")
    n_seeds: int = Field(default=1, description="Number of evaluation seeds.")
    seeds: List[int] = Field(default_factory=list)
    metrics: List[MetricResult] = Field(default_factory=list)
    baselines: List[str] = Field(
        default_factory=list, description="Baseline identities compared against."
    )
    acceptance_criteria: Dict[str, Any] = Field(
        default_factory=dict, description="Configured acceptance thresholds."
    )
    status: EvaluationStatus = Field(default=EvaluationStatus.PENDING)
    outcome: Optional[str] = Field(
        default=None,
        description="Measured outcome: 'success', 'failure', 'inconclusive' when evaluated.",
    )
    limitations: List[str] = Field(
        default_factory=list, description="Known limitations / uncertainty disclosures."
    )
    created_at: Optional[str] = None
    extensions: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "forbid"}
