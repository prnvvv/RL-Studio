"""Canonical end-to-end scenario: controller -> LangGraph -> serialised output.

This is the acceptance test for Person 3's vertical slice.  It drives the real
``VerificationAgentController`` (the entry point an API layer would call) over
the canonical warehouse reward-scaling evidence and injects the deterministic
offline investigator, so the complete pipeline runs with **no live Meta Model
API request**.

Only the external model boundary is substituted.  Every other stage is the
production implementation: input adaptation, normalisation, context building,
intent parsing, requirement extraction and dispatch, the five deterministic
checkers, aggregation, serialisation, and in-memory persistence.
"""

from __future__ import annotations

from typing import Any

from backend.verification.agent.agent_controller import VerificationAgentController
from backend.verification.input.input_adapter import adapt_input
from backend.verification.llm.mock_client import OfflineMockMetaClient
from backend.verification.models import CheckStatus
from backend.verification.storage.verification_store import InMemoryVerificationStore
from unit_testing.conftest import DEVELOPER_INTENT, make_evidence


def _canonical_input() -> Any:
    return adapt_input(
        {
            "agent_metadata": {"agent_id": "agent_e2e", "agent_type": "ppo"},
            "developer_intent": DEVELOPER_INTENT,
            "environment_config": {"learning_rate": 0.001},
            "training_config": {"learning_rate": 0.001, "seed": 42},
            "execution_evidence": make_evidence(),
        }
    )


def test_canonical_reward_scaling_pipeline_end_to_end() -> None:
    store = InMemoryVerificationStore()
    client = OfflineMockMetaClient()
    controller = VerificationAgentController(model_client=client, storage=store)

    result = controller.run_verification(_canonical_input())
    output = controller.run_verification_output(_canonical_input())

    # 1. Deterministic verdict comes from the broken contract, not from the model.
    assert result.overall_status is CheckStatus.FAIL
    reward = next(
        check
        for check in result.requirements.values()
        if check.details and check.details.get("source") == "reward_check"
    )
    assert reward.status is CheckStatus.FAIL
    assert reward.expected == 25.0
    assert reward.actual == 5.0
    assert reward.evidence_refs == ["evt_reward_goal_1"]

    # 2. Serialised output keeps the contract vocabulary and provenance.
    assert output["contract_status"] == "violation"
    assert output["overall_status"] == "fail"
    assert output["environment_version"] == "warehouse_v1"
    assert output["run_identifier"] == "run_test_1"
    assert not output.get("verification_id")  # never invented

    # 3. The offline investigator ran in-process and is labelled as offline.
    diagnosis = output["diagnosis"]
    assert diagnosis["status"] == "completed"
    assert diagnosis["provider"] == "offline_mock"
    assert diagnosis["result"]["_metadata"]["live_request"] is False
    assert diagnosis["result"]["root_cause_status"] == "unresolved"
    assert diagnosis["result"]["confidence"] is None
    assert diagnosis["guardrail_violations"] == []
    assert len(client.calls) == 2  # one call per controller invocation

    # 3b. Advisory analysis is serialised and never alters the verdict.
    assert output["anomalies"] == []
    assert output["consistency"]["status"] == "consistent"
    assert output["consistency"]["consistent"] is True
    assert output["consistency"]["evidence_available"] is True

    # 4. Every passing check is backed by real evidence references.
    for check in output["requirements"].values():
        if check["status"] == "pass":
            assert check["evidence_refs"]

    # 5. Persistence is append-only; one input and one result per invocation.
    assert store.snapshot() == {"inputs": 2, "results": 2, "reports": 0}


def test_canonical_scenario_can_be_reported_and_persisted() -> None:
    store = InMemoryVerificationStore()
    controller = VerificationAgentController(
        model_client=OfflineMockMetaClient(), storage=store
    )

    result = controller.run_verification(_canonical_input())
    report = controller.build_verification_report(
        result,
        diagnosis={"status": "completed", "provider": "offline_mock"},
        recommendations=["Re-run with the configured goal reward of 25 before recovery."],
        limitations=["Offline deterministic investigator; no Meta Model API request was made."],
    )

    assert report.summary
    assert "evt_reward_goal_1" in report.evidence_refs
    assert store.snapshot() == {"inputs": 1, "results": 1, "reports": 1}
