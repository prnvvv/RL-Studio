"""Deterministic verification pipeline scenarios.

Every assertion is based on recorded evidence.  Where evidence is missing the
expected outcome is ``unknown``/``not_evaluable``, never ``pass``.
"""

from __future__ import annotations

from typing import Any

from backend.verification.agent.verification_agent import (
    run_verification,
    run_verification_state,
)
from backend.verification.models import (
    CheckStatus,
    RequirementSource,
    RequirementType,
    VerificationRequirement,
)
from backend.verification.tools.event_checker import execute_check as check_events
from unit_testing.conftest import make_evidence, make_payload


def _event_requirement(**metadata: Any) -> VerificationRequirement:
    return VerificationRequirement(
        description="event constraint",
        type=RequirementType.event,
        source=RequirementSource.developer_confirmed,
        metadata=metadata,
    )


def _statuses(out: dict[str, Any]) -> dict[str, str]:
    return {
        check["requirement_id"]: check["status"]
        for check in out["requirements"].values()
    }


# ---------------------------------------------------------------------------
# 1-2. Canonical reward-scaling scenario
# ---------------------------------------------------------------------------


def test_canonical_reward_scaling_violation_is_detected(
    payload: dict[str, Any],
) -> None:
    out = run_verification(payload)

    assert out["overall_status"] == "fail"
    assert out["contract_status"] == "violation"
    reward = next(
        check
        for check in out["requirements"].values()
        if check["details"] and check["details"].get("source") == "reward_check"
    )
    assert reward["status"] == "fail"
    assert reward["expected"] == 25.0
    assert reward["actual"] == 5.0
    assert reward["evidence_refs"] == ["evt_reward_goal_1"]


def test_matching_reward_passes_with_real_evidence(payload: dict[str, Any]) -> None:
    payload["execution_evidence"]["reward"]["observed"] = 25.0

    out = run_verification(payload)

    reward = next(
        check
        for check in out["requirements"].values()
        if check["details"] and check["details"].get("source") == "reward_check"
    )
    assert reward["status"] == "pass"
    assert reward["evidence_refs"] == ["evt_reward_goal_1"]


# ---------------------------------------------------------------------------
# 3. Missing evidence never becomes a pass
# ---------------------------------------------------------------------------


def test_missing_observed_reward_is_unknown_not_zero(payload: dict[str, Any]) -> None:
    payload["execution_evidence"]["reward"] = {"expected": 25.0}

    out = run_verification(payload)

    reward = next(
        check
        for check in out["requirements"].values()
        if check["details"] and check["details"].get("source") == "reward_check"
    )
    assert reward["status"] == "unknown"
    assert reward["actual"] is None
    assert out["overall_status"] == "unknown"
    assert out["contract_status"] == "not_evaluable"


def test_absent_evidence_keeps_every_requirement_unevaluated() -> None:
    out = run_verification(make_payload(evidence=None))

    assert out["overall_status"] == "unknown"
    assert out["contract_status"] == "not_evaluable"
    checks = list(out["requirements"].values())
    # Execution-evidence requirements cannot be evaluated; a configuration
    # contract may still pass because its evidence is the supplied config.
    assert all(check["status"] in {"unknown", "pass"} for check in checks)
    assert any(check["status"] == "unknown" for check in checks)
    assert all(check["evidence_refs"] for check in checks if check["status"] == "pass")
    assert all(
        check["actual"] is None for check in checks if check["status"] == "unknown"
    )


# ---------------------------------------------------------------------------
# 4-5. Malformed requests fail closed
# ---------------------------------------------------------------------------


def test_missing_developer_intent_produces_no_requirements() -> None:
    out = run_verification(make_payload(intent=None, evidence=make_evidence()))

    assert out["overall_status"] == "unknown"
    assert out["contract_status"] == "not_evaluable"
    assert out["requirements"] == {}
    assert "No developer intent supplied" in out["error"]


def test_missing_agent_metadata_blocks_without_synthesis() -> None:
    payload = make_payload(evidence=make_evidence())
    del payload["agent_metadata"]

    state = run_verification_state(payload)

    assert state.error == "Verification input requires agent_metadata."
    assert state.input is None
    assert state.requirements == []


# ---------------------------------------------------------------------------
# 6-8. Event constraints
# ---------------------------------------------------------------------------


def test_missing_required_event_is_a_violation_only_when_evidence_is_complete() -> None:
    requirement = _event_requirement(
        required_event="goal_reached", constraint="required_event"
    )
    events = [{"event_id": "evt_1", "event_type": "step"}]

    complete = check_events(
        "check_event",
        requirement,
        recorded_events=events,
        required_event="goal_reached",
        evidence_complete=True,
    )
    incomplete = check_events(
        "check_event",
        requirement,
        recorded_events=events,
        required_event="goal_reached",
        evidence_complete=False,
    )

    assert complete.status is CheckStatus.FAIL
    assert incomplete.status is CheckStatus.UNKNOWN
    assert incomplete.expected is None  # no expectation was invented


def test_recorded_forbidden_event_is_a_violation(payload: dict[str, Any]) -> None:
    payload["developer_intent"] = "The agent must never emit the collision event."
    payload["execution_evidence"]["events"].append(
        {"event_id": "evt_collision", "event_type": "collision"}
    )

    out = run_verification(payload)

    assert out["overall_status"] == "fail"
    event_check = next(iter(out["requirements"].values()))
    assert event_check["status"] == "fail"
    assert event_check["evidence_refs"] == ["evt_collision"]


def test_absent_forbidden_event_passes_with_recorded_refs(
    payload: dict[str, Any],
) -> None:
    payload["developer_intent"] = "The agent must never emit the collision event."

    out = run_verification(payload)

    event_check = next(iter(out["requirements"].values()))
    assert event_check["status"] == "pass"
    assert event_check["evidence_refs"] == ["evt_1", "evt_2"]


def test_unnamed_forbidden_event_stays_unknown(payload: dict[str, Any]) -> None:
    payload["developer_intent"] = "The agent must never emit the forbidden event."

    out = run_verification(payload)

    event_check = next(iter(out["requirements"].values()))
    assert event_check["status"] == "unknown"
    assert out["overall_status"] != "pass"


def test_duplicate_event_deliveries_do_not_inflate_counts() -> None:
    requirement = _event_requirement(
        event_count={"goal_reached": 2}, constraint="event_count"
    )
    duplicated = [
        {"event_id": "evt_2", "event_type": "goal_reached"},
        {"event_id": "evt_2", "event_type": "goal_reached"},
    ]

    result = check_events(
        "check_event",
        requirement,
        recorded_events=duplicated,
        event_count={"goal_reached": 2},
        evidence_complete=True,
    )

    assert result.status is CheckStatus.FAIL
    assert result.actual == {"goal_reached": 1}
    assert result.evidence_refs == ["evt_2"]


# ---------------------------------------------------------------------------
# 9-11. Episode outcome and step bounds
# ---------------------------------------------------------------------------


def test_successful_termination_requires_goal_attainment(
    payload: dict[str, Any],
) -> None:
    payload["developer_intent"] = "The episode must terminate successfully."

    out = run_verification(payload)

    episode_check = next(iter(out["requirements"].values()))
    assert episode_check["status"] == "pass"
    assert episode_check["actual"] == "goal_attained"
    assert episode_check["evidence_refs"] == ["ep_0001"]


def test_truncated_episode_violates_successful_termination(
    payload: dict[str, Any],
) -> None:
    payload["developer_intent"] = "The episode must terminate successfully."
    payload["execution_evidence"]["episode"] = {
        "episode_id": "ep_0002",
        "terminated": False,
        "truncated": True,
        "goal_reached": False,
        "steps": 500,
    }

    out = run_verification(payload)

    episode_check = next(iter(out["requirements"].values()))
    assert episode_check["status"] == "fail"
    assert episode_check["actual"] == "truncated"


def test_max_steps_bound_is_evaluated_from_recorded_length(
    payload: dict[str, Any],
) -> None:
    payload["developer_intent"] = "The episode must finish within 200 steps."

    within = run_verification(payload)
    payload["execution_evidence"]["episode"]["steps"] = 500
    exceeded = run_verification(payload)

    within_check = next(iter(within["requirements"].values()))
    exceeded_check = next(iter(exceeded["requirements"].values()))
    assert within_check["status"] == "pass"
    assert within_check["actual"] == 40
    assert exceeded_check["status"] == "fail"
    assert exceeded_check["actual"] == 500


def test_max_steps_without_recorded_length_is_unknown(payload: dict[str, Any]) -> None:
    payload["developer_intent"] = "The episode must finish within 200 steps."
    payload["execution_evidence"]["episode"] = {
        "episode_id": "ep_0003",
        "terminated": True,
    }

    out = run_verification(payload)

    episode_check = next(iter(out["requirements"].values()))
    assert episode_check["status"] == "unknown"
    assert episode_check["actual"] is None


# ---------------------------------------------------------------------------
# 12. Configuration contracts
# ---------------------------------------------------------------------------


def test_learning_rate_mismatch_is_a_violation(payload: dict[str, Any]) -> None:
    payload["developer_intent"] = "The learning rate must remain at 0.001."
    payload["training_config"]["learning_rate"] = 0.01

    out = run_verification(payload)

    config_check = next(iter(out["requirements"].values()))
    assert config_check["status"] == "fail"
    assert config_check["expected"] == 0.001
    assert config_check["actual"] == 0.01


# ---------------------------------------------------------------------------
# 13. Aggregate invariants
# ---------------------------------------------------------------------------


def test_mandatory_failure_can_never_be_reported_as_pass(
    payload: dict[str, Any],
) -> None:
    out = run_verification(payload)
    statuses = _statuses(out)

    assert "fail" in statuses.values()
    assert out["overall_status"] != "pass"
