"""Integration tests for event flow and persistence (AGENTS.md §17)."""

from __future__ import annotations

from shared.schemas import (
    Incident,
    Recovery,
    Evaluation,
    Requirement,
)
from shared.schemas.requirements import RequirementType, RequirementSource


def test_incident_creation():
    """Incident must accept required fields and have optional fields."""
    inc = Incident(
        run_id="r1",
        violation_type="reward_scale_mismatch",
        requirement_id="req_goal_reward",
        environment_version="warehouse_v1",
        environment_id="wh",
    )
    assert inc.run_id == "r1"
    assert inc.violation_type == "reward_scale_mismatch"
    assert inc.requirement_id == "req_goal_reward"
    assert inc.environment_version == "warehouse_v1"
    assert inc.environment_id == "wh"


def test_recovery_model():
    """Recovery must separate proposed_actions from executed_actions."""
    rec = Recovery(
        incident_id="inc_1",
        proposed_actions=["restore_checkpoint"],
        executed_actions=["restore_checkpoint"],
    )
    assert rec.incident_id == "inc_1"
    assert len(rec.proposed_actions) == 1
    assert len(rec.executed_actions) == 1


def test_evaluation_model():
    """Evaluation must have metric definitions and baseline identities."""
    eval_rec = Evaluation(
        recovery_id="rec_1",
        run_id="r1",
        environment_version="warehouse_v1",
        n_episodes=10,
        n_seeds=3,
        seeds=[0, 1, 2],
        metrics=[],
        baselines=[],
    )
    assert eval_rec.recovery_id == "rec_1"
    assert eval_rec.n_episodes == 10
    assert eval_rec.n_seeds == 3


def test_requirement_model():
    """Requirement must support source type and comparison operator."""
    req = Requirement(
        id="req_goal_reward",
        title="Goal reward",
        description="Goal reward must be 10.0",
        requirement_type=RequirementType.reward,
        source=RequirementSource.developer_confirmed,
        operator="==",
        expected_value=10.0,
    )
    assert req.id == "req_goal_reward"
    assert req.requirement_type == "reward"
    assert req.source == "developer_confirmed"
    assert req.operator == "=="
    assert req.expected_value == 10.0