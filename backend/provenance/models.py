"""Provenance models and lineage records (AGENTS.md §7, §10).

Tracks artifact fingerprints, checkpoint associations, and
environment/configuration lineage across runs, incidents,
recoveries, and evaluations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ArtifactFingerprint(BaseModel):
    """Fingerprint of a checkpoint or model artifact."""

    artifact_id: str
    checksum: str
    version: str
    environment_version: str
    algorithm: str
    created_at: str = Field(default_factory=utc_now)


class LineageRecord(BaseModel):
    """Lineage trace linking run → events → checkpoints → incidents."""

    project_id: str
    experiment_id: str
    run_id: str
    environment_version: str
    agent_config_fingerprint: str
    checkpoint_ids: List[str] = Field(default_factory=list)
    event_ids: List[str] = Field(default_factory=list)
    incident_ids: List[str] = Field(default_factory=list)
    recovery_ids: List[str] = Field(default_factory=list)
    evaluation_ids: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class ExposureStatus(str, Enum):
    """Provenance-derived exposure status (AGENTS.md §13)."""

    EXPOSED = "exposed"
    POTENTIALLY_AFFECTED = "potentially_affected"
    UNKNOWN = "unknown"