"""Conditional-routing tests for the LangGraph verification workflow.

These tests exercise the *graph edges*, not the individual node bodies: they
prove that the compiled graph skips work when an earlier stage fails and that
the advisory investigation only runs when it is both requested and actionable.
"""

from __future__ import annotations

from typing import Any

from backend.verification.agent.verification_agent import run_verification_state
from backend.verification.llm.mock_client import OfflineMockMetaClient
from unit_testing.conftest import make_evidence, make_payload


def _diagnosis(state: Any) -> dict[str, Any]:
    assert isinstance(state.output, dict)
    diagnosis = state.output.get("diagnosis")
    assert isinstance(diagnosis, dict)
    return diagnosis


def test_normalize_failure_short_circuits_to_complete(
    payload: dict[str, Any],
) -> None:
    """A missing agent_metadata stops at normalize; no planning or checks run."""
    del payload["agent_metadata"]

    state = run_verification_state(payload)

    assert state.error == "Verification input requires agent_metadata."
    assert state.step == "complete"
    assert state.requirements == []
    assert state.check_results == {}
    assert _diagnosis(state)["status"] == "not_requested"


def test_plan_failure_short_circuits_to_complete(payload: dict[str, Any]) -> None:
    """Empty developer intent never reaches the check stage."""
    payload["developer_intent"] = "   "

    state = run_verification_state(payload)

    assert state.error is not None
    assert "No developer intent" in state.error
    assert state.check_results == {}
    assert state.step == "complete"


def test_passing_run_skips_investigation_even_with_provider(
    payload: dict[str, Any], offline_client: OfflineMockMetaClient
) -> None:
    """A PASS verdict must not trigger the advisory model at all."""
    payload["execution_evidence"]["reward"]["observed"] = 25.0

    state = run_verification_state(payload, model_client=offline_client)

    assert state.overall_status is not None
    assert state.overall_status.value == "pass"
    assert state.investigation_pending is False
    assert offline_client.calls == []
    assert _diagnosis(state)["status"] == "not_requested"


def test_failing_run_routes_to_investigation(
    payload: dict[str, Any], offline_client: OfflineMockMetaClient
) -> None:
    """A non-PASS verdict with a provider is routed to the investigate node."""
    state = run_verification_state(payload, model_client=offline_client)

    assert state.investigation_pending is True
    assert len(offline_client.calls) == 1
    diagnosis = _diagnosis(state)
    assert diagnosis["status"] in {"completed", "completed_with_warnings"}
    assert diagnosis["provider"] == "offline_mock"
    # The model is advisory: the deterministic verdict is unchanged.
    assert state.overall_status is not None
    assert state.overall_status.value == "fail"


def test_investigation_can_be_disabled_explicitly(
    payload: dict[str, Any], offline_client: OfflineMockMetaClient
) -> None:
    """``investigate=False`` skips the provider while checks still fail."""
    payload["investigate"] = False

    state = run_verification_state(payload, model_client=offline_client)

    assert state.overall_status is not None
    assert state.overall_status.value == "fail"
    assert offline_client.calls == []
    assert _diagnosis(state)["status"] == "not_requested"


def test_missing_provider_reports_unavailable_not_simulated(
    payload: dict[str, Any],
) -> None:
    """Without a provider the diagnosis is ``unavailable``, never fabricated."""
    state = run_verification_state(make_payload(evidence=make_evidence()))

    assert state.investigation_pending is True
    diagnosis = _diagnosis(state)
    assert diagnosis["status"] == "unavailable"
    assert diagnosis["provider"] is None
