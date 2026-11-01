"""Advisory investigation behind the provider boundary — fully offline.

The deterministic pipeline is exercised unchanged; only the external model
boundary is substituted.  These tests assert that the model can never change a
deterministic verdict and that a model failure never breaks verification.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from backend.verification.agent.verification_agent import run_verification
from backend.verification.llm.mock_client import (
    MODEL_NAME,
    PROVIDER_NAME,
    OfflineMockMetaClient,
)
from backend.verification.models import (
    RequirementSource,
    RequirementType,
    VerificationRequirement,
)
from backend.verification.result_validator import validate_investigation_result
from unit_testing.conftest import make_payload

FULL_INVESTIGATION = {
    "summary": "The observed goal reward differs from the contract.",
    "observed_facts": [
        {"fact": "observed reward was 5.0", "evidence_refs": ["evt_reward_goal_1"]}
    ],
    "candidate_causes": [
        {
            "hypothesis": "reward scaling changed",
            "evidence_refs": ["evt_reward_goal_1"],
            "confidence": None,
            "root_cause_status": "unresolved",
        }
    ],
    "supporting_evidence": [],
    "contradicting_evidence": [],
    "root_cause_status": "unresolved",
    "recommended_tests": [
        "compare the configured goal reward with the observed reward"
    ],
    "limitations": ["no environment source excerpt was supplied"],
    "confidence": None,
}


class _StubClient:
    """Minimal provider used to prove the model cannot alter the verdict."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def investigate(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request)
        return dict(self.response)


class _FailingClient:
    def investigate(self, request: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("provider exploded")


def test_offline_mock_completes_without_any_live_request(
    payload: dict[str, Any],
) -> None:
    client = OfflineMockMetaClient()

    out = run_verification(payload, model_client=client)

    diagnosis = out["diagnosis"]
    assert diagnosis["status"] == "completed"
    assert diagnosis["provider"] == PROVIDER_NAME
    assert diagnosis["model"] == MODEL_NAME
    assert diagnosis["result"]["_metadata"]["live_request"] is False
    assert diagnosis["result"]["confidence"] is None
    assert diagnosis["result"]["root_cause_status"] == "unresolved"
    assert len(client.calls) == 1
    assert out["overall_status"] == "fail"


def test_offline_mock_reports_missing_evidence_honestly() -> None:
    client = OfflineMockMetaClient()
    payload = make_payload(evidence=None)

    out = run_verification(payload, model_client=client)

    diagnosis = out["diagnosis"]
    assert diagnosis["status"] == "completed"
    result = diagnosis["result"]
    assert result["root_cause_status"] == "unresolved"
    incomplete = [
        fact
        for fact in result["observed_facts"]
        if fact["fact"] == "requirement_check_result" and fact["status"] != "pass"
    ]
    assert incomplete
    assert all(fact["actual"] is None for fact in incomplete)
    assert all("evidence_refs" not in fact for fact in incomplete)
    assert out["overall_status"] == "unknown"


def test_model_cannot_upgrade_a_deterministic_violation(
    payload: dict[str, Any],
) -> None:
    stub = _StubClient(
        {
            **FULL_INVESTIGATION,
            "root_cause_status": "confirmed",
            "overall_status": "pass",
            "requirements": {"anything": {"status": "pass"}},
        }
    )

    out = run_verification(payload, model_client=stub)

    assert out["overall_status"] == "fail"
    assert out["contract_status"] == "violation"
    diagnosis = out["diagnosis"]
    assert diagnosis["result"]["root_cause_status"] == "unresolved"
    assert any("downgraded" in problem for problem in diagnosis["problems"])
    assert (
        diagnosis["result"]["overall_status"] == "pass"
    )  # copied, still advisory only


def test_provider_failure_keeps_deterministic_result(payload: dict[str, Any]) -> None:
    out = run_verification(payload, model_client=_FailingClient())

    assert out["overall_status"] == "fail"
    assert out["diagnosis"]["status"] == "unavailable"
    assert "RuntimeError" in out["diagnosis"]["reason"]


def test_no_provider_is_reported_as_not_requested_on_pass(
    payload: dict[str, Any],
) -> None:
    payload["execution_evidence"]["reward"]["observed"] = 25.0

    out = run_verification(payload)

    assert out["overall_status"] == "pass"
    assert out["diagnosis"] == {"status": "not_requested"}


def test_no_provider_on_failure_is_reported_as_unavailable(
    payload: dict[str, Any],
) -> None:
    out = run_verification(payload)

    assert out["overall_status"] == "fail"
    assert out["diagnosis"]["status"] == "unavailable"
    assert "deterministic verification stands" in out["diagnosis"]["reason"]


def test_investigation_prompt_carries_evidence_and_no_credentials(
    payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("META_AI_API_KEY", "sk-must-never-appear")
    stub = _StubClient(FULL_INVESTIGATION)

    run_verification(payload, model_client=stub)

    assert len(stub.requests) == 1
    prompt = stub.requests[0]["prompt"]
    assert "evt_reward_goal_1" in prompt
    assert "goal reward" in prompt
    assert "sk-must-never-appear" not in prompt
    assert "{execution_evidence}" not in prompt
    assert "{expected_behaviour}" not in prompt


def test_confirmed_root_cause_without_evidence_is_downgraded() -> None:
    normalised, problems = validate_investigation_result(
        {**FULL_INVESTIGATION, "root_cause_status": "confirmed"}
    )

    assert normalised["root_cause_status"] == "unresolved"
    assert any("downgraded" in problem for problem in problems)


def test_missing_investigation_fields_are_reported_not_invented() -> None:
    normalised, problems = validate_investigation_result({"summary": "only a summary"})

    assert normalised["confidence"] is None
    assert normalised["observed_facts"] == []
    assert normalised["root_cause_status"] == "unknown"
    assert problems


def test_requirement_model_rejects_unsupported_type() -> None:
    with pytest.raises(ValidationError):
        VerificationRequirement(
            description="unknown contract",
            type="not-a-requirement-type",  # type: ignore[arg-type]
            source=RequirementSource.developer_confirmed,
        )
    assert RequirementType.reward.value == "reward"
