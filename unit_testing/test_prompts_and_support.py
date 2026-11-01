"""Supporting units: prompts, serialisation, storage, controller, reporting.

These tests cover the supporting contracts that the pipeline depends on.  They
do not re-test the pipeline itself.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.verification.agent.agent_controller import VerificationAgentController
from backend.verification.analysis.execution_analyzer import analyse_execution_evidence
from backend.verification.exceptions import InputValidationError, PersistenceError
from backend.verification.intent.intent_parser import parse_intent
from backend.verification.llm.mock_client import OfflineMockMetaClient
from backend.verification.llm.prompts import get_prompt
from backend.verification.models import (
    AgentMetadata,
    CheckStatus,
    RequirementSource,
    RequirementType,
    VerificationCheckResult,
    VerificationContext,
    VerificationInput,
    VerificationRequirement,
)
from backend.verification.report_builder import build_report
from backend.verification.result_serializer import serialize_check_result
from backend.verification.storage.verification_store import InMemoryVerificationStore
from backend.verification.tools.event_checker import execute_check as check_events
from unit_testing.conftest import DEVELOPER_INTENT, make_evidence

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def test_partial_prompt_substitution_never_raises() -> None:
    prompt = get_prompt("evidence_investigation", execution_evidence="EVIDENCE-BLOCK")

    assert "EVIDENCE-BLOCK" in prompt
    assert "{expected_behaviour}" in prompt  # left visible, not silently blanked
    assert "{execution_evidence}" not in prompt


def test_unknown_prompt_name_is_rejected() -> None:
    with pytest.raises(ValueError):
        get_prompt("not_a_prompt")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Intent metadata
# ---------------------------------------------------------------------------


def test_unnamed_forbidden_event_is_not_invented() -> None:
    parsed = parse_intent("The agent must never emit the forbidden event.")

    metadata = parsed["requirements"][0]["metadata"]
    assert metadata["forbidden_event"] is None
    assert metadata["constraint"] == "forbidden_event"


def test_named_forbidden_event_is_captured() -> None:
    parsed = parse_intent("The agent must never emit the collision event.")

    assert parsed["requirements"][0]["metadata"]["forbidden_event"] == "collision"


def test_step_bound_is_exposed_as_metadata() -> None:
    parsed = parse_intent("The episode must finish within 200 steps.")

    requirement = parsed["requirements"][0]
    assert requirement["metadata"]["max_steps"] == 200
    assert requirement["type"] == RequirementType.termination.value


def test_successful_termination_is_stricter_than_plain_termination() -> None:
    successful = parse_intent("The episode must terminate successfully.")
    plain = parse_intent("The episode must terminate.")

    assert successful["requirements"][0]["expected_value"] == "goal_attained"
    assert plain["requirements"][0]["expected_value"] is True


def test_empty_intent_is_unsupported_not_invented() -> None:
    parsed = parse_intent("   ")

    assert parsed["unsupported"] is True
    assert parsed["requirements"] == []
    assert parsed["ambiguity_reason"] == "empty intent"


# ---------------------------------------------------------------------------
# Event ordering
# ---------------------------------------------------------------------------


def test_out_of_order_delivery_violates_declared_order() -> None:
    requirement = VerificationRequirement(
        description="event order",
        type=RequirementType.event,
        source=RequirementSource.developer_confirmed,
    )
    events = [
        {"event_id": "evt_b", "event_type": "goal_reached"},
        {"event_id": "evt_a", "event_type": "episode_started"},
    ]

    result = check_events(
        "check_event",
        requirement,
        recorded_events=events,
        expected_event_order=["episode_started", "goal_reached"],
        evidence_complete=True,
    )

    assert result.status is CheckStatus.FAIL
    assert result.actual == ["goal_reached", "episode_started"]


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def test_serialisation_adds_contract_status_without_removing_fields() -> None:
    requirement = VerificationRequirement(
        description="goal reward == 25",
        type=RequirementType.reward,
        source=RequirementSource.developer_confirmed,
        expected_value=25.0,
    )
    check_result = VerificationCheckResult(
        requirement_id=requirement.id,
        status=CheckStatus.FAIL,
        expected=25.0,
        actual=5.0,
        evidence_refs=["evt_1"],
    )

    payload = serialize_check_result(check_result)

    assert payload["status"] == "fail"
    assert payload["contract_status"] == "violation"
    assert payload["expected"] == 25.0
    assert payload["evidence_refs"] == ["evt_1"]


# ---------------------------------------------------------------------------
# Evidence analysis
# ---------------------------------------------------------------------------


def test_analysis_reports_missing_evidence_instead_of_guessing() -> None:
    summary = analyse_execution_evidence(None)

    assert summary["has_any_evidence"] is False
    assert summary["events"] == {"supplied": False, "count": None, "event_types": {}}
    assert set(summary["missing_evidence"]) == {
        "observed_reward",
        "episode",
        "events",
        "metrics",
        "configuration",
    }


def test_analysis_summarises_supplied_evidence() -> None:
    summary = analyse_execution_evidence(make_evidence())

    assert summary["events"]["count"] == 2
    assert summary["events"]["event_types"] == {"step": 1, "goal_reached": 1}
    assert summary["metrics"]["episode_reward"]["count"] == 2
    assert summary["metrics"]["episode_reward"]["min"] == 5.0
    assert summary["metrics"]["episode_reward"]["max"] == 6.0
    assert summary["missing_evidence"] == ["configuration"]


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def test_report_records_unavailable_investigation_as_a_limitation() -> None:
    from backend.verification.models import VerificationResult

    result = VerificationResult(overall_status=CheckStatus.UNKNOWN)
    report = build_report(
        result, diagnosis={"status": "unavailable", "reason": "no credentials"}
    )

    limitations = report.limitations or []
    assert report.recommendations == []
    assert any("unavailable" in limitation for limitation in limitations)
    assert any("did not pass" in limitation for limitation in limitations)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _input() -> VerificationInput:
    return VerificationInput(
        agent_metadata=AgentMetadata(agent_id="agent_store"),
        developer_intent=DEVELOPER_INTENT,
        execution_evidence=make_evidence(),
        environment_config={"learning_rate": 0.001},
        training_config={"learning_rate": 0.001, "seed": 7},
    )


def test_storage_is_append_only_and_returns_copies() -> None:
    store = InMemoryVerificationStore()
    verification_input = _input()

    first = store.save_verification_input(verification_input)
    second = store.save_verification_input(verification_input)

    assert first != second
    assert store.snapshot()["inputs"] == 2

    loaded = store.load_verification_input(first)
    loaded.developer_intent = "mutated locally"
    assert store.load_verification_input(first).developer_intent == DEVELOPER_INTENT


def test_storage_rejects_unknown_identifiers() -> None:
    store = InMemoryVerificationStore()

    with pytest.raises(PersistenceError):
        store.load_verification_result("vres_999999")
    with pytest.raises(PersistenceError):
        store.load_verification_input("")


# ---------------------------------------------------------------------------
# Controller (typed service boundary)
# ---------------------------------------------------------------------------


def test_controller_runs_the_workflow_and_persists_results() -> None:
    store = InMemoryVerificationStore()
    controller = VerificationAgentController(
        model_client=OfflineMockMetaClient(), storage=store
    )
    verification_input = _input()
    context = VerificationContext(
        run_identifier="run_test_1",
        environment_identifier="warehouse",
        environment_version="warehouse_v1",
        input=verification_input,
    )

    result = controller.run_verification(verification_input, context)

    assert result.overall_status is CheckStatus.FAIL
    assert result.requirements
    assert result.summary and "Overall status: fail" in result.summary
    assert store.snapshot() == {"inputs": 1, "results": 1, "reports": 0}

    stored_id = store.storage_ids()["results"][0]
    assert store.load_verification_result(stored_id).overall_status is CheckStatus.FAIL


def test_controller_report_is_persisted_only_when_requested() -> None:
    store = InMemoryVerificationStore()
    controller = VerificationAgentController(storage=store)
    verification_input = _input()
    result = controller.run_verification(verification_input)

    assert store.snapshot()["reports"] == 0
    controller.build_verification_report(result, diagnosis={"status": "not_requested"})
    assert store.snapshot()["reports"] == 1


def test_controller_rejects_non_typed_requests() -> None:
    controller = VerificationAgentController()

    with pytest.raises(InputValidationError):
        controller.run_verification({"agent_metadata": {}}, None)  # type: ignore[arg-type]


def test_controller_output_payload_is_json_safe() -> None:
    controller = VerificationAgentController()
    verification_input = _input()

    payload: dict[str, Any] = controller.run_verification_output(verification_input)

    assert payload["overall_status"] == "fail"
    assert payload["contract_status"] == "violation"
    assert isinstance(payload["requirements"], dict)
