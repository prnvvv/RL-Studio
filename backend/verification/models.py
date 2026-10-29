"""Canonical data models for the verification subsystem.

Defines Pydantic v2 models for agent metadata, verification input/context,
requirements, plans, check results, reports, evidence references, metric
observations, and anomaly observations. All models use snake_case field names,
support optional/extensible fields, and are JSON-serializable.
"""

from __future__ import annotations
from pydantic import BaseModel, Field, model_validator

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Literal, Union
import uuid


# ---------------------------------------------------------------------------
# Identifier convention: the repository uses string UUIDs (v4 / random).
# We generate stable UUID v4 strings via the module-level helper.


def _generate_uuid_v4() -> str:
    """Return a new UUID v4 string."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RequirementSource(Enum):
    developer_confirmed = "developer_confirmed"
    test_derived = "test_derived"
    code_inferred = "code_inferred"
    documentation_inferred = "documentation_inferred"
    system_invariant = "system_invariant"


class RequirementType(Enum):
    reward = "reward"
    termination = "termination"
    observation = "observation"
    action_space = "action_space"
    grid_goal = "grid_goal"
    collision = "collision"
    metric = "metric"
    configuration = "configuration"
    event = "event"


class CheckStatus(Enum):
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"
    ERROR = "error"


class AnomalyType(Enum):
    statistical = "statistical"
    distribution_shift = "distribution_shift"
    reward_deviation = "reward_deviation"
    observation_corruption = "observation_corruption"


# ---------------------------------------------------------------------------
# 1. AgentMetadata
# ---------------------------------------------------------------------------


class AgentMetadata(BaseModel):
    """Metadata identifying the RL agent and its configuration."""

    agent_id: str = Field(default_factory=_generate_uuid_v4)
    agent_type: Optional[str] = None
    agent_template: Optional[str] = None
    template_version: Optional[str] = None
    configuration_fingerprint: Optional[str] = None
    extensions: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "allow"}

    def model_dump(self, *args, **kwargs):
        """JSON-serializable dump using snake_case field names."""
        # Pydantic v2: field names are already snake_case; remove any snake_alias
        # argument that was carried over from v1 patterns.
        kwargs.pop("snake_alias", None)
        return super().model_dump(*args, **kwargs)


# ---------------------------------------------------------------------------
# 2. VerificationInput
# ---------------------------------------------------------------------------


class VerificationInput(BaseModel):
    """Structured input to the verification system."""

    agent_metadata: AgentMetadata
    environment_config: Optional[Dict[str, Any]] = Field(
        default=None, description="Raw env config dict"
    )
    training_config: Optional[Dict[str, Any]] = Field(
        default=None, description="Raw training hyper-params"
    )
    developer_intent: Optional[str] = Field(
        default=None, description="Natural-language description of intended behaviour"
    )
    execution_evidence: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional raw evidence dict; prefer EvidenceReference entries instead"
        ),
    )
    extensions: Dict[str, Any] = Field(
        default_factory=dict, description="Extension fields for future schema evolution"
    )

    model_config = {"populate_by_name": True, "extra": "allow"}

    @model_validator(mode="after")
    def _ensure_agent_metadata(self) -> "VerificationInput":
        if self.agent_metadata is None:
            raise ValueError("VerificationInput.agent_metadata is required")
        return self


# ---------------------------------------------------------------------------
# 3. VerificationContext
# ---------------------------------------------------------------------------


class VerificationContext(BaseModel):
    """Runtime context linking a verification request to a run/environment."""

    run_identifier: Optional[str] = Field(
        default=None, description="e.g. run_id, experiment_id"
    )
    environment_identifier: Optional[str] = Field(
        default=None, description="e.g. warehouse_v1, sim_01"
    )
    environment_version: Optional[str] = Field(
        default=None, description="e.g. v1, v2"
    )
    input: VerificationInput
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = Field(default="1.0")

    model_config = {"populate_by_name": True, "extra": "allow"}


# ---------------------------------------------------------------------------
# 4. VerificationRequirement
# ---------------------------------------------------------------------------


class VerificationRequirement(BaseModel):
    """A machine-checkable requirement derived from developer intent."""

    id: str = Field(default_factory=_generate_uuid_v4)
    description: str
    source: RequirementSource = Field(
        default=RequirementSource.developer_confirmed
    )
    type: RequirementType
    expected_value: Optional[Any] = Field(
        default=None, description="e.g. 100, a goal name, a range"
    )
    comparison_operator: Optional[
        Literal["==", "!=", ">=", "<=", ">", "<"]
    ] = Field(default=None, description="e.g. ==, >, <")
    tolerance: Optional[float] = Field(
        default=None, ge=0, description="Absolute tolerance for numeric comparisons"
    )
    is_mandatory: bool = Field(
        default=True, description="Whether this requirement blocks PASS when failed/unverifiable"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Free-form key-value pairs"
    )
    extensions: Dict[str, Any] = Field(
        default_factory=dict, description="Extension fields"
    )

    model_config = {"populate_by_name": True, "extra": "allow"}


# ---------------------------------------------------------------------------
# 5. VerificationPlanStep
# ---------------------------------------------------------------------------


class VerificationPlanStep(BaseModel):
    """A single step in a verification workflow plan."""

    step_id: str = Field(default_factory=_generate_uuid_v4)
    check_tool_id: str = Field(
        description="Registered check/tool identifier, e.g. check_reward_scale"
    )
    description: str
    dependencies: List[str] = Field(
        default_factory=list, description="Step IDs this step depends on"
    )
    evidence_requirements: List[str] = Field(
        default_factory=list,
        description="List of EvidenceReference IDs required",
    )
    order: Optional[int] = Field(default=None, description="Execution order")
    status: CheckStatus = Field(default=CheckStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"populate_by_name": True, "extra": "allow"}


# ---------------------------------------------------------------------------
# 6. VerificationPlan
# ---------------------------------------------------------------------------


class VerificationPlan(BaseModel):
    """An ordered workflow of deterministic checks and optional anomaly steps."""

    plan_id: str = Field(default_factory=_generate_uuid_v4)
    steps: List[VerificationPlanStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[str] = Field(
        default=None, description="e.g. developer, meta_ai_agent"
    )
    extensions: Dict[str, Any] = Field(
        default_factory=dict, description="Extension fields"
    )

    model_config = {"populate_by_name": True, "extra": "allow"}


# ---------------------------------------------------------------------------
# 7. VerificationCheckResult
# ---------------------------------------------------------------------------


class VerificationCheckResult(BaseModel):
    """Result of evaluating one requirement against available evidence."""

    requirement_id: str
    status: CheckStatus
    expected: Optional[Any] = Field(
        default=None, description="The expected value from the requirement"
    )
    actual: Optional[Any] = Field(
        default=None, description="The observed/actual value from execution"
    )
    tolerance: Optional[float] = Field(
        default=None, ge=0, description="Absolute tolerance for comparison"
    )
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="List of EvidenceReference IDs supporting this result",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Free-form details; must not contain secrets, credentials, or raw prompts"
        ),
    )
    is_mandatory: bool = Field(
        default=True,
        description="Whether this requirement blocks PASS when failed/unverifiable",
    )

    model_config = {"populate_by_name": True, "extra": "allow"}


# ---------------------------------------------------------------------------
# 8. VerificationResult
# ---------------------------------------------------------------------------


class VerificationResult(BaseModel):
    """Overall verification result aggregating per-requirement check outcomes."""

    verification_id: str = Field(default_factory=_generate_uuid_v4)
    overall_status: CheckStatus = Field(default=CheckStatus.UNKNOWN)
    requirements: Dict[str, VerificationCheckResult] = Field(
        default_factory=dict,
        description="Map from requirement ID to VerificationCheckResult",
    )
    summary: Optional[str] = Field(
        default=None, description="Human-readable summary of the overall result"
    )
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="List of top-level EvidenceReference IDs",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = Field(default="1.0")
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "extra": "allow"}


# ---------------------------------------------------------------------------
# 10. VerificationReport
# ---------------------------------------------------------------------------


class VerificationReport(BaseModel):
    """A packaged report generated after a verification investigation."""

    report_id: str = Field(default_factory=_generate_uuid_v4)
    verification: Optional[VerificationResult] = Field(
        default=None, description="The associated VerificationResult"
    )
    summary: Optional[str] = Field(
        default=None, description="Human-readable high-level summary"
    )
    recommendations: Optional[List[str]] = Field(
        default_factory=list, description="Actionable recommendations"
    )
    limitations: Optional[List[str]] = Field(
        default_factory=list, description="Known limitations of the investigation"
    )
    evidence_refs: List[str] = Field(
        default_factory=list, description="List of top-level EvidenceReference IDs"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = Field(default="1.0")

    model_config = {"populate_by_name": True, "extra": "allow"}


# ---------------------------------------------------------------------------
# 11. EvidenceReference
# ---------------------------------------------------------------------------


class EvidenceReference(BaseModel):
    """A stable reference to a piece of execution evidence."""

    id: str = Field(default_factory=_generate_uuid_v4)
    source: str = Field(
        description="e.g. run_id, environment_id, checkpoint_id, event_id"
    )
    run_identifier: Optional[str] = Field(
        default=None, description="e.g. the run_id this evidence belongs to"
    )
    environment_identifier: Optional[str] = Field(
        default=None, description="e.g. warehouse_v1"
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    location: Optional[str] = Field(
        default=None,
        description=(
            "Reference/path rather than raw payload; e.g. s3://bucket/key, "
            "db_table.row_id, log_file_path"
        ),
    )
    extensions: Dict[str, Any] = Field(
        default_factory=dict, description="Extension fields"
    )

    model_config = {"populate_by_name": True, "extra": "allow"}


# ---------------------------------------------------------------------------
# 12. MetricObservation
# ---------------------------------------------------------------------------


class MetricObservation(BaseModel):
    """A single metric observation recorded during an RL training run."""

    metric_name: str
    value: float
    unit: Optional[str] = Field(
        default=None, description="e.g. 'rewards', 'steps', 'collisions'"
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    episode_id: Optional[str] = Field(default=None, description="e.g. episode_42")
    timestep: Optional[int] = Field(default=None, description="e.g. timestep at measurement")
    run_identifier: Optional[str] = Field(
        default=None, description="e.g. run_id, experiment_id"
    )

    model_config = {"populate_by_name": True, "extra": "allow"}


# ---------------------------------------------------------------------------
# 13. AnomalyObservation
# ---------------------------------------------------------------------------


class AnomalyObservation(BaseModel):
    """An anomaly signal detected from metric/evidence observations.

    Distinguishes a detector's output from a confirmed fault.  The downstream
    verification engine must not treat an anomaly score as proof of a fault
    without supporting deterministic requirement checks.
    """

    anomaly_type: AnomalyType
    score: Optional[float] = Field(
        default=None, ge=0, le=1, description="Normalized anomaly score when available"
    )
    threshold: Optional[float] = Field(
        default=None, ge=0, description="Detection threshold that triggered this anomaly"
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evidence_refs: List[str] = Field(
        default_factory=list, description="Supporting EvidenceReference IDs"
    )
    description: Optional[str] = Field(
        default=None, description="Human-readable description"
    )

    model_config = {"populate_by_name": True, "extra": "allow"}


# ---------------------------------------------------------------------------
# End of module
# ---------------------------------------------------------------------------