"""Integration tests for anomaly detection and consistency checking.

Both stages run inside the real LangGraph workflow and are advisory: they
surface signals and contradictions but never change the deterministic status.
"""

from __future__ import annotations

from typing import Any

from backend.verification.agent.verification_agent import run_verification
from backend.verification.consistency_checker import detect_evidence_contradictions
from backend.verification.evidence_validator import extract_evidence
from unit_testing.conftest import make_evidence, make_payload

PASSING_INTENT = (
    "The episode must terminate successfully. "
    "The agent must never emit the collision event. "
    "The learning rate must remain at 0.001."
)


def _passing_evidence(**overrides: Any) -> dict[str, Any]:
    return make_evidence(**overrides)


def _series(*values: float, name: str = "episode_reward") -> list[dict[str, Any]]:
    return [
        {"id": f"met_{index}", "name": name, "value": value}
        for index, value in enumerate(values)
    ]


def test_workflow_runs_analysis_and_reports_no_anomaly_for_a_stable_series() -> None:
    out = run_verification(
        make_payload(
            intent=PASSING_INTENT,
            evidence=_passing_evidence(metrics=_series(1, 2, 3, 4, 5, 6, 7, 8)),
        )
    )

    assert out["overall_status"] == "pass"
    assert out["anomalies"] == []
    assert out["consistency"]["status"] == "consistent"
    assert out["consistency"]["consistent"] is True


def test_anomaly_is_reported_but_cannot_manufacture_a_failure() -> None:
    metrics = _series(1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1000)

    out = run_verification(
        make_payload(
            intent=PASSING_INTENT,
            evidence=_passing_evidence(metrics=metrics),
        )
    )

    assert out["overall_status"] == "pass"
    assert out["contract_status"] == "pass"
    assert len(out["anomalies"]) == 1
    anomaly = out["anomalies"][0]
    assert anomaly["anomaly_type"] == "statistical"
    assert anomaly["evidence_refs"] == ["met_11"]


def test_missing_evidence_is_not_reported_as_consistent() -> None:
    out = run_verification(make_payload(evidence=None))

    consistency = out["consistency"]
    assert consistency["status"] == "not_evaluable"
    assert consistency["consistent"] is False
    assert consistency["evidence_available"] is False


def test_invalid_metric_records_are_skipped_without_crashing_analysis() -> None:
    evidence = _passing_evidence(
        metrics=[
            {"id": "met_bad", "name": "episode_reward", "value": "not-a-number"},
            "not-a-record",
            {"id": "met_ok", "name": "episode_reward", "value": 2.0},
        ]
    )

    out = run_verification(make_payload(intent=PASSING_INTENT, evidence=evidence))

    assert out["overall_status"] == "pass"
    assert out["anomalies"] == []


def test_contradictory_episode_evidence_is_explicitly_reported() -> None:
    evidence = _passing_evidence()
    evidence["episode"] = {
        "episode_id": "ep_contradiction",
        "terminated": False,
        "truncated": False,
        "goal_reached": True,
        "steps": 40,
    }

    out = run_verification(
        make_payload(intent="The episode must terminate successfully.", evidence=evidence)
    )

    kinds = {item["kind"] for item in out["consistency"]["contradictions"]}
    assert "episode_goal_without_termination" in kinds
    assert out["consistency"]["status"] == "contradictory"


def test_duplicate_event_with_conflicting_type_is_a_contradiction() -> None:
    evidence = _passing_evidence(
        events=[
            {"event_id": "evt_dup", "event_type": "goal_reached", "sequence": 1},
            {"event_id": "evt_dup", "event_type": "collision", "sequence": 2},
        ]
    )

    contradictions = detect_evidence_contradictions(extract_evidence(evidence))

    assert [item["kind"] for item in contradictions] == [
        "conflicting_duplicate_event"
    ]
    assert contradictions[0]["evidence_refs"] == ["evt_dup"]


def test_duplicate_metric_with_conflicting_value_is_a_contradiction() -> None:
    evidence = _passing_evidence(
        metrics=[
            {"id": "met_a", "name": "loss", "value": 1.0, "episode_id": "ep_1"},
            {"id": "met_b", "name": "loss", "value": 9.0, "episode_id": "ep_1"},
        ]
    )

    contradictions = detect_evidence_contradictions(extract_evidence(evidence))

    assert [item["kind"] for item in contradictions] == [
        "conflicting_duplicate_metric"
    ]
    assert set(contradictions[0]["evidence_refs"]) == {"met_a", "met_b"}


def test_configuration_conflict_between_environment_and_training_is_reported() -> None:
    payload = make_payload(intent=PASSING_INTENT, evidence=_passing_evidence())
    payload["environment_config"] = {"learning_rate": 0.001}
    payload["training_config"] = {"learning_rate": 0.5, "seed": 42}

    out = run_verification(payload)

    kinds = {item["kind"] for item in out["consistency"]["contradictions"]}
    assert "configuration_conflict" in kinds


def test_analysis_does_not_override_a_deterministic_violation() -> None:
    out = run_verification(make_payload(evidence=_passing_evidence()))

    assert out["overall_status"] == "fail"
    assert out["consistency"]["status"] == "consistent"
