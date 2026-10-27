"""End-to-end test for the canonical warehouse reward-scaling scenario (AGENTS.md §21)."""

from __future__ import annotations

import json
import pytest

from shared.schemas import (
    Incident,
    Recovery,
    Evaluation,
    RewardObservedEvent,
    EpisodeStartedEvent,
    EpisodeEndedEvent,
    SourceComponent,
    new_uuid,
    SCHEMA_VERSION,
)
from backend.fault_injection.faults import FaultType, FaultConfig, FaultInjector
from shared.schemas.requirements import RequirementType, RequirementSource


def test_reward_scaling_fault_changes_observed_reward():
    """A reward-scaling fault must multiply the goal reward by the scale factor."""
    injector = FaultInjector(FaultConfig(
        fault_type=FaultType.REWARD_SCALING,
        scale=5.0,
        trigger_step=0,
        trigger_episode=0,
        seed=42,
    ))
    original_reward = 10.0
    scaled = injector.apply_reward_scaling(original_reward, step=5, episode=1)
    assert scaled == 50.0


def test_event_schema_validity():
    """Events must validate against their schema version."""
    event = RewardObservedEvent(
        schema_version=SCHEMA_VERSION,
        event_id=new_uuid(),
        event_type="reward_observed",
        run_id="r1",
        episode_id="e1",
        timestep=1,
        environment_version="warehouse_v1",
        source_component=SourceComponent.ENVIRONMENT,
        payload={"actual_reward": 25.0, "reward_kind": "goal", "requirement_id": "req_goal_reward"},
    )
    assert event.event_type == "reward_observed"
    assert event.payload.actual_reward == 25.0


def test_incident_references_event_ids():
    """Incident must reference real event IDs."""
    inc = Incident(
        run_id="r1",
        violation_type="reward_scale_mismatch",
        evidence_event_ids=["evt_1", "evt_2"],
        environment_version="warehouse_v1",
    )
    assert len(inc.evidence_event_ids) == 2


def test_requirement_violation_event():
    """RequirementViolationEvent must capture expected vs actual."""
    from shared.schemas.events import RequirementViolationEvent

    rve = RequirementViolationEvent(
        schema_version=SCHEMA_VERSION,
        event_id=new_uuid(),
        event_type="requirement_violation",
        run_id="r1",
        episode_id="e1",
        timestep=1,
        environment_version="warehouse_v1",
        source_component=SourceComponent.VERIFICATION,
        payload={
            "requirement_id": "req_goal_reward",
            "requirement_version": "1",
            "comparison": "==",
            "expected": 10.0,
            "actual": 5.0,
            "severity": "high",
        },
    )
    assert rve.payload.expected == 10.0
    assert rve.payload.actual == 5.0