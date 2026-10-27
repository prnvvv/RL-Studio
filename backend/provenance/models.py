from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    checkpoint = "checkpoint"
    trajectory = "trajectory"
    experience = "experience"
    policy_update = "policy_update"
    configuration = "configuration"
    log = "log"
    dataset = "dataset"
    other = "other"


class ArtifactStatus(str, Enum):
    available = "available"
    missing = "missing"
    superseded = "superseded"
    deleted = "deleted"
    invalid = "invalid"
    unknown = "unknown"


class IntegrityStatus(str, Enum):
    verified = "verified"
    unverified = "unverified"
    mismatch = "mismatch"
    missing = "missing"


class ProvenanceStatus(str, Enum):
    complete = "complete"
    incomplete = "incomplete"
    unknown = "unknown"
    conflict = "conflict"


class LineageCompleteness(str, Enum):
    complete = "complete"
    partial = "partial"
    unknown = "unknown"


class ImpactStatus(str, Enum):
    confirmed_exposed = "confirmed_exposed"
    potentially_affected = "potentially_affected"
    not_exposed_based_on_recorded_lineage = "not_exposed_based_on_recorded_lineage"
    unknown_incomplete_lineage = "unknown_incomplete_lineage"


class RunRegistration(BaseModel):
    run_id: Optional[str] = None
    project_id: Optional[str] = None
    experiment_id: Optional[str] = None
    environment_id: Optional[str] = None
    environment_version: Optional[str] = None
    agent_config_fingerprint: Optional[str] = None
    status: str = "created"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ArtifactRegistration(BaseModel):
    artifact_id: Optional[str] = None
    run_id: str
    artifact_type: ArtifactType
    artifact_path: str
    artifact_hash: Optional[str] = None
    artifact_version: Optional[str] = None
    artifact_status: Optional[ArtifactStatus] = None
    artifact_created_at: Optional[datetime] = None
    parent_artifact_id: Optional[str] = None
    checkpoint_id: Optional[str] = None
    checkpoint_path: Optional[str] = None
    policy_version: Optional[str] = None
    trajectory_id: Optional[str] = None
    experience_id: Optional[str] = None
    policy_update_id: Optional[str] = None
    environment_id: Optional[str] = None
    environment_version: Optional[str] = None
    agent_config_fingerprint: Optional[str] = None
    episode_id: Optional[str] = None
    timestep: Optional[int] = None
    update_index: Optional[int] = None
    included_state_components: list[str] = Field(default_factory=list)
    metadata_schema_version: str = "1.0"
    metadata: dict[str, Any] = Field(default_factory=dict)


class IncidentRegistration(BaseModel):
    incident_id: str
    run_id: str
    status: str = "detected"
    verification_id: Optional[str] = None
    environment_id: Optional[str] = None
    environment_version: Optional[str] = None
    requirement_id: Optional[str] = None
    severity: Optional[str] = None
    detection_method: Optional[str] = None
    summary: Optional[str] = None
    evidence_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    fault_type: Optional[str] = None
    source_environment_version: Optional[str] = None
    corruption_start_timestep: Optional[int] = None
    corruption_end_timestep: Optional[int] = None


class Run(BaseModel):
    run_id: str
    project_id: Optional[str] = None
    experiment_id: Optional[str] = None
    environment_id: Optional[str] = None
    environment_version: Optional[str] = None
    agent_config_fingerprint: Optional[str] = None
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class Artifact(BaseModel):
    artifact_id: str
    run_id: str
    artifact_type: ArtifactType
    artifact_path: str
    artifact_hash: Optional[str] = None
    artifact_version: Optional[str] = None
    artifact_status: ArtifactStatus
    artifact_created_at: datetime
    parent_artifact_id: Optional[str] = None
    checkpoint_id: Optional[str] = None
    checkpoint_path: Optional[str] = None
    policy_version: Optional[str] = None
    trajectory_id: Optional[str] = None
    experience_id: Optional[str] = None
    policy_update_id: Optional[str] = None
    environment_id: Optional[str] = None
    environment_version: Optional[str] = None
    agent_config_fingerprint: Optional[str] = None
    episode_id: Optional[str] = None
    timestep: Optional[int] = None
    update_index: Optional[int] = None
    included_state_components: list[str] = Field(default_factory=list)
    integrity_status: IntegrityStatus
    metadata_schema_version: str = "1.0"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ArtifactLink(BaseModel):
    link_id: str
    run_id: str
    from_artifact_id: str
    to_artifact_id: str
    relation: str
    created_at: datetime


class RunArtifactList(BaseModel):
    run_id: str
    count: int
    artifacts: list[Artifact]


class ProvenanceTrace(BaseModel):
    provenance_id: str
    run_id: str
    provenance_status: ProvenanceStatus
    lineage_completeness: LineageCompleteness
    source_environment_version: Optional[str] = None
    environment_id: Optional[str] = None
    environment_version: Optional[str] = None
    artifact_count: int
    artifacts: list[Artifact] = Field(default_factory=list)
    links: list[ArtifactLink] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class Incident(BaseModel):
    incident_id: str
    run_id: str
    verification_id: Optional[str] = None
    environment_id: Optional[str] = None
    environment_version: Optional[str] = None
    requirement_id: Optional[str] = None
    status: str
    severity: Optional[str] = None
    detection_method: Optional[str] = None
    summary: Optional[str] = None
    evidence_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    source_environment_version: Optional[str] = None
    corruption_start_timestep: Optional[int] = None
    corruption_end_timestep: Optional[int] = None
    fault_type: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ImpactAnalysis(BaseModel):
    impact_id: str
    incident_id: str
    run_id: str
    impact_status: ImpactStatus
    impact_score: Optional[float] = None
    source_environment_version: Optional[str] = None
    corruption_start_timestep: Optional[int] = None
    corruption_end_timestep: Optional[int] = None
    affected_artifact_ids: list[str] = Field(default_factory=list)
    affected_trajectory_ids: list[str] = Field(default_factory=list)
    affected_policy_update_ids: list[str] = Field(default_factory=list)
    affected_checkpoint_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    completed_at: Optional[datetime] = None
