"""Canonical cross-module data contracts for Self-Healing RL Studio.

This package is the single source of truth for inter-module Pydantic models
(root AGENTS.md §7).  Modules (environments, training, monitoring,
fault_injection, verification, diagnosis, provenance, recovery, evaluation)
MUST import these models rather than redefining equivalents.

The models are intentionally dependency-light (pure ``pydantic`` + stdlib) so
any module — including the gymnasium-based RL engine — can import them without
pulling in tensor libraries.

Naming / conventions:
- Snake-case field names.
- Identifiers are opaque strings (see AGENTS.md §7.1); display names are never
  used as identifiers.
- ``expected_*`` and ``actual_*`` fields are kept distinct and must never be
  merged; an expected value is absent (None) when no confirmed contract exists.
- All timestamps are timezone-aware UTC.
- ``extra="forbid"`` is enforced; forward-compat fields use ``extensions``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"
"""Canonical schema version for all shared contracts in this package."""


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    """Return a freshly generated stable identifier string (UUIDv4)."""
    return str(uuid.uuid4())


from .contracts import (
    CompatibilityCheck,
    Evaluation,
    EvaluationStatus,
    Incident,
    IncidentStatus,
    MetricResult,
    Recovery,
    RecoveryAction,
    RecoveryStatus,
    RootCauseStatus,
    ViolationSeverity,
)
from .events import (
    CheckpointWrittenEvent,
    CollisionEvent,
    EpisodeEndedEvent,
    EpisodeStartedEvent,
    ExecutionEvent,
    ExecutionEventType,
    FaultInjectedEvent,
    RequirementViolationEvent,
    RewardObservedEvent,
    SourceComponent,
)
from .requirements import (
    ComparisonOperator,
    Requirement,
    RequirementSource,
    RequirementType,
)

__all__ = [
    "SCHEMA_VERSION",
    "utc_now",
    "new_uuid",
    # events
    "ExecutionEvent",
    "EpisodeStartedEvent",
    "EpisodeEndedEvent",
    "RewardObservedEvent",
    "CollisionEvent",
    "CheckpointWrittenEvent",
    "FaultInjectedEvent",
    "RequirementViolationEvent",
    "ExecutionEventType",
    "SourceComponent",
    # requirements
    "Requirement",
    "RequirementSource",
    "RequirementType",
    "ComparisonOperator",
    # contracts
    "Incident",
    "IncidentStatus",
    "ViolationSeverity",
    "RootCauseStatus",
    "Recovery",
    "RecoveryAction",
    "RecoveryStatus",
    "CompatibilityCheck",
    "Evaluation",
    "EvaluationStatus",
    "MetricResult",
]
