"""Canonical execution-event contract (AGENTS.md §7.2).

An event is a durable, schema-validated record of something that happened
during a run.  Events carry stable IDs, UTC timestamps, and ordering metadata
so that incidents, diagnoses, and provenance traces can reference them without
relying on in-memory state.

The base :class:`ExecutionEvent` holds the common envelope fields.  Each typed
event (episode metrics, checkpoint, collision, fault, requirement violation,
...) subclasses it and adds a validated ``payload``.  Consumers should always
carry ``schema_version`` so older events remain readable during evolution.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from . import SCHEMA_VERSION, new_uuid, utc_now


class SourceComponent(str, Enum):
    """Component that produced an event.  Stable, stringly-typed-safe."""

    ENVIRONMENT = "environment"
    TRAINING = "training"
    MONITORING = "monitoring"
    FAULT_INJECTION = "fault_injection"
    VERIFICATION = "verification"
    DIAGNOSIS = "diagnosis"
    PROVENANCE = "provenance"
    RECOVERY = "recovery"
    EVALUATION = "evaluation"


# ---------------------------------------------------------------------------
# Common envelope
# ---------------------------------------------------------------------------


class ExecutionEvent(BaseModel):
    """Common envelope for every execution event.

    Subclasses add a validated ``payload``.  ``expected_*`` fields are never
    merged with ``actual_*`` fields; an expected value is absent when no
    confirmed contract exists (AGENTS.md §7.2).
    """

    schema_version: str = Field(default=SCHEMA_VERSION, description="Event schema version.")
    event_id: str = Field(default_factory=new_uuid, description="Stable unique event ID.")
    event_type: str = Field(description="Discriminator matching the concrete event class.")
    run_id: str = Field(description="Owning training run identifier.")
    project_id: Optional[str] = Field(default=None, description="Owning project identifier.")
    experiment_id: Optional[str] = Field(default=None, description="Owning experiment identifier.")
    environment_id: Optional[str] = Field(default=None, description="Environment identifier.")
    environment_version: Optional[str] = Field(
        default=None, description="Immutable environment version, e.g. 'warehouse_v1'."
    )
    episode_id: Optional[str] = Field(default=None, description="Episode identifier, if applicable.")
    rollout_id: Optional[str] = Field(default=None, description="Rollout identifier, if applicable.")
    training_update_id: Optional[str] = Field(
        default=None, description="PPO update / iteration identifier, if applicable."
    )
    timestep: int = Field(default=0, description="Global timestep counter at the event.")
    sequence: int = Field(
        default=0,
        description=(
            "Monotonic per-run sequence number for ordering; 0 when not assigned. "
            "Consumers must not assume sequence is globally unique across runs."
        ),
    )
    timestamp: datetime = Field(
        default_factory=utc_now, description="UTC event timestamp (timezone-aware)."
    )
    source_component: SourceComponent = Field(
        description="Component that produced this event."
    )
    source_version: Optional[str] = Field(
        default=None, description="Software version of the producing component."
    )
    correlation_id: Optional[str] = Field(
        default=None, description="Correlation ID linking related events (run/incident/etc).")
    cause_id: Optional[str] = Field(
        default=None, description="ID of the event that caused this one, when known.")
    extensions: Dict[str, Any] = Field(
        default_factory=dict,
        description="Documented extension fields for forward compatibility.",
    )

    model_config = {"populate_by_name": True, "extra": "forbid"}


# ---------------------------------------------------------------------------
# Typed events
# ---------------------------------------------------------------------------


class EpisodeStartedEvent(ExecutionEvent):
    event_type: str = "episode_started"

    class Payload(BaseModel, extra="forbid"):
        seed: Optional[int] = None

    payload: Payload


class EpisodeEndedEvent(ExecutionEvent):
    event_type: str = "episode_ended"

    class Payload(BaseModel, extra="forbid"):
        total_reward: float
        steps: int
        terminated: bool = Field(description="True if a success/absorb terminal state was reached.")
        truncated: bool = Field(
            description="True if the episode ended by a non-succeeding limit (step budget)."
        )
        success: bool = Field(description="True if the goal was reached this episode.")

    payload: Payload


class RewardObservedEvent(ExecutionEvent):
    """A single observed reward.

    ``expected_reward`` is present only when a confirmed contract defines an
    expected value for this event; otherwise it is absent (None).  Actual and
    expected rewards are never merged.
    """

    event_type: str = "reward_observed"

    class Payload(BaseModel, extra="forbid"):
        actual_reward: float
        expected_reward: Optional[float] = Field(
            default=None,
            description="Expected value from a confirmed contract, or None when none applies.",
        )
        reward_kind: str = Field(
            default="other",
            description="Origin of the reward, e.g. 'goal', 'step', 'collision'.",
        )
        requirement_id: Optional[str] = Field(
            default=None, description="Confirmed requirement that defines expected_reward."
        )

    payload: Payload


class CollisionEvent(ExecutionEvent):
    event_type: str = "collision"

    class Payload(BaseModel, extra="forbid"):
        agent_position: list[float]
        collision_target: Optional[str] = Field(
            default=None, description="What was collided with (obstacle id, wall, goal)."
        )
        penalty: float = Field(default=0.0, description="Reward penalty applied for the collision.")

    payload: Payload


class CheckpointWrittenEvent(ExecutionEvent):
    event_type: str = "checkpoint_written"

    class Payload(BaseModel, extra="forbid"):
        checkpoint_id: str
        path: str
        integrity_hash: str = Field(description="SHA-256 hash of the checkpoint bytes.")
        training_update_id: Optional[str] = None

    payload: Payload


class FaultInjectedEvent(ExecutionEvent):
    event_type: str = "fault_injected"

    class Payload(BaseModel, extra="forbid"):
        fault_type: str = Field(description="Allow-listed fault identifier.")
        parameters: Dict[str, Any]
        trigger_timestep: int = Field(
            description="Timestep at which the fault becomes active."
        )
        stage: str = Field(
            description="Trigger boundary: 'before_step' or 'after_step'."
        )
        run_id: Optional[str] = None

    payload: Payload


class RequirementViolationEvent(ExecutionEvent):
    """Emission of a deterministic contract violation (produced by verification)."""

    event_type: str = "requirement_violation"

    class Payload(BaseModel, extra="forbid"):
        requirement_id: str
        requirement_version: str
        comparison: Optional[str] = Field(
            default=None, description="Operator, e.g. '==' or '>='."
        )
        expected: Any = None
        actual: Any = None
        tolerance: Optional[float] = None
        severity: str = Field(description="e.g. 'high', 'medium', 'low'.")
        incident_id: Optional[str] = None

    payload: Payload


class ExecutionEventType(BaseModel):
    """Documentation helper listing the known event discriminators."""

    known_types: tuple[str, ...] = (
        "episode_started",
        "episode_ended",
        "reward_observed",
        "collision",
        "checkpoint_written",
        "fault_injected",
        "requirement_violation",
    )
