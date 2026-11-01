"""Shared fixtures for the Person 3 verification test suite.

These tests are strictly offline.  No request may leave the process: the Meta
Model API boundary is either the deterministic ``OfflineMockMetaClient`` or an
``httpx.MockTransport``.  Nothing here reads real credentials.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.verification.llm.mock_client import OfflineMockMetaClient

#: Reward-scaling fault: the developer expects 25, the faulty environment pays 5.
DEVELOPER_INTENT = (
    "The goal reward must equal 25. "
    "The episode must terminate successfully. "
    "The agent must never emit the collision event. "
    "The learning rate must remain at 0.001."
)


def make_evidence(**overrides: Any) -> dict[str, Any]:
    """Return a fresh, complete evidence mapping for the warehouse scenario."""
    evidence: dict[str, Any] = {
        "run_id": "run_test_1",
        "environment_id": "warehouse",
        "environment_version": "warehouse_v1",
        "reward": {
            "expected": 25.0,
            "observed": 5.0,
            "event_id": "evt_reward_goal_1",
        },
        "episode": {
            "episode_id": "ep_0001",
            "terminated": True,
            "truncated": False,
            "goal_reached": True,
            "steps": 40,
        },
        "events": [
            {"event_id": "evt_1", "event_type": "step", "sequence": 1},
            {"event_id": "evt_2", "event_type": "goal_reached", "sequence": 2},
        ],
        "metrics": [
            {"id": "met_1", "name": "episode_reward", "value": 5.0},
            {"id": "met_2", "name": "episode_reward", "value": 6.0},
        ],
        "evidence_complete": True,
    }
    evidence.update(overrides)
    return evidence


def make_payload(
    *,
    intent: str | None = DEVELOPER_INTENT,
    evidence: dict[str, Any] | None = None,
    agent_metadata: dict[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Build a workflow input mapping from explicit values only."""
    payload: dict[str, Any] = {
        "agent_metadata": (
            {"agent_id": "agent_test", "agent_type": "ppo"}
            if agent_metadata is None
            else agent_metadata
        ),
        "environment_config": {"learning_rate": 0.001},
        "training_config": {"learning_rate": 0.001, "seed": 42},
    }
    if intent is not None:
        payload["developer_intent"] = intent
    if evidence is not None:
        payload["execution_evidence"] = evidence
    payload.update(overrides)
    return payload


@pytest.fixture()
def offline_client() -> OfflineMockMetaClient:
    return OfflineMockMetaClient()


@pytest.fixture()
def evidence() -> dict[str, Any]:
    return make_evidence()


@pytest.fixture()
def payload(evidence: dict[str, Any]) -> dict[str, Any]:
    return make_payload(evidence=evidence)
