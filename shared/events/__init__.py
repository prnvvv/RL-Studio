"""Canonical execution-event contract (AGENTS.md §7.2).

Re-exports from shared.schemas for inter-module consistency.
Events carry stable IDs, UTC timestamps, and ordering metadata
so that incidents, diagnoses, and provenance traces can reference
them without relying on in-memory state.
"""

from __future__ import annotations

from shared.schemas import (
    SCHEMA_VERSION,
    CheckpointWrittenEvent,
    CollisionEvent,
    EpisodeEndedEvent,
    EpisodeStartedEvent,
    ExecutionEvent,
    FaultInjectedEvent,
    RequirementViolationEvent,
    RewardObservedEvent,
    SourceComponent,
    new_uuid,
    utc_now,
)

__all__ = [
    "SCHEMA_VERSION",
    "CheckpointWrittenEvent",
    "CollisionEvent",
    "EpisodeEndedEvent",
    "EpisodeStartedEvent",
    "ExecutionEvent",
    "FaultInjectedEvent",
    "RequirementViolationEvent",
    "RewardObservedEvent",
    "SourceComponent",
    "new_uuid",
    "utc_now",
]