from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ..utils import dumps, new_id, utc_now_iso
from ._common import row_to_dict


_JSON_FIELDS = {
    "evaluation_metrics_json": "evaluation_metrics",
    "comparison_results_json": "comparison_results",
    "acceptance_criteria_json": "acceptance_criteria",
    "seeds_json": "seeds",
    "evidence_ids_json": "evidence_ids",
    "warnings_json": "warnings",
    "errors_json": "errors",
    "details_json": "details",
}

_BOOL_FIELDS = ("recovery_verified",)


def create_evaluation(
    conn: sqlite3.Connection,
    *,
    incident_id: str,
    evaluation_status: str,
    recovery_verification_status: str,
    recovery_verified: bool = False,
    recovery_id: Optional[str] = None,
    baseline_run_id: Optional[str] = None,
    recovered_run_id: Optional[str] = None,
    evaluation_environment_version: Optional[str] = None,
    baseline_mean_reward: Optional[float] = None,
    recovered_mean_reward: Optional[float] = None,
    baseline_success_rate: Optional[float] = None,
    recovered_success_rate: Optional[float] = None,
    baseline_episode_length: Optional[float] = None,
    recovered_episode_length: Optional[float] = None,
    reward_improvement: Optional[float] = None,
    success_rate_improvement: Optional[float] = None,
    evaluation_metrics: Optional[dict[str, Any]] = None,
    comparison_results: Optional[dict[str, Any]] = None,
    acceptance_criteria: Optional[dict[str, Any]] = None,
    episode_count: Optional[int] = None,
    seeds: Optional[list[int]] = None,
    evidence_ids: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
    errors: Optional[list[str]] = None,
    details: Optional[dict[str, Any]] = None,
    idempotency_key: Optional[str] = None,
    completed_at: Optional[str] = None,
) -> dict[str, Any]:
    evaluation_id = new_id("evaluation")
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO evaluations(
            evaluation_id, incident_id, recovery_id, baseline_run_id,
            recovered_run_id, evaluation_status, evaluation_environment_version,
            baseline_mean_reward, recovered_mean_reward, baseline_success_rate,
            recovered_success_rate, baseline_episode_length,
            recovered_episode_length, reward_improvement,
            success_rate_improvement, evaluation_metrics_json,
            comparison_results_json, acceptance_criteria_json,
            recovery_verification_status, recovery_verified, episode_count,
            seeds_json, evidence_ids_json, warnings_json, errors_json,
            details_json, idempotency_key, created_at, completed_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
        """,
        (
            evaluation_id,
            incident_id,
            recovery_id,
            baseline_run_id,
            recovered_run_id,
            evaluation_status,
            evaluation_environment_version,
            baseline_mean_reward,
            recovered_mean_reward,
            baseline_success_rate,
            recovered_success_rate,
            baseline_episode_length,
            recovered_episode_length,
            reward_improvement,
            success_rate_improvement,
            dumps(evaluation_metrics or {}),
            dumps(comparison_results or {}),
            dumps(acceptance_criteria or {}),
            recovery_verification_status,
            1 if recovery_verified else 0,
            episode_count,
            dumps(seeds or []),
            dumps(evidence_ids or []),
            dumps(warnings or []),
            dumps(errors or []),
            dumps(details or {}),
            idempotency_key,
            now,
            completed_at or now,
        ),
    )
    return get_evaluation(conn, evaluation_id)  # type: ignore[return-value]


def get_evaluation(
    conn: sqlite3.Connection, evaluation_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM evaluations WHERE evaluation_id = ?", (evaluation_id,)
    ).fetchone()
    return row_to_dict(
        row, json_fields=_JSON_FIELDS, bool_fields=_BOOL_FIELDS
    )


def get_evaluation_by_idempotency(
    conn: sqlite3.Connection, idempotency_key: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM evaluations WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    return row_to_dict(
        row, json_fields=_JSON_FIELDS, bool_fields=_BOOL_FIELDS
    )


def list_evaluations_for_incident(
    conn: sqlite3.Connection, incident_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM evaluations WHERE incident_id = ? ORDER BY created_at",
        (incident_id,),
    ).fetchall()
    return [
        row_to_dict(row, json_fields=_JSON_FIELDS, bool_fields=_BOOL_FIELDS)
        for row in rows
    ]  # type: ignore[misc]
