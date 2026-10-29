from __future__ import annotations

import sqlite3
from typing import Any

from ..utils import dumps, new_id, utc_now_iso
from ._common import row_to_dict

_ASSESSMENT_JSON_FIELDS = {
    "compatibility_json": "compatibility",
    "lineage_gaps_json": "lineage_gaps",
    "evidence_ids_json": "evidence_ids",
    "warnings_json": "warnings",
    "errors_json": "errors",
    "details_json": "details",
}

_RECOVERY_JSON_FIELDS = {
    "proposed_actions_json": "proposed_actions",
    "executed_actions_json": "executed_actions",
    "preflight_json": "preflight",
    "evidence_ids_json": "evidence_ids",
    "warnings_json": "warnings",
    "errors_json": "errors",
    "details_json": "details",
}


def create_assessment(
    conn: sqlite3.Connection,
    *,
    incident_id: str,
    recovery_eligibility: str,
    recovery_strategy: str,
    recovery_reason: str | None = None,
    source_checkpoint_id: str | None = None,
    target_environment_version: str | None = None,
    target_agent_config_fingerprint: str | None = None,
    compatibility: list[dict[str, Any]] | None = None,
    lineage_gaps: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    details: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    assessment_id = new_id("assessment")
    conn.execute(
        """
        INSERT INTO recovery_assessments(
            recovery_assessment_id, incident_id, recovery_eligibility,
            recovery_strategy, recovery_reason, source_checkpoint_id,
            target_environment_version, target_agent_config_fingerprint,
            compatibility_json, lineage_gaps_json, evidence_ids_json,
            warnings_json, errors_json, details_json, idempotency_key,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            assessment_id,
            incident_id,
            recovery_eligibility,
            recovery_strategy,
            recovery_reason,
            source_checkpoint_id,
            target_environment_version,
            target_agent_config_fingerprint,
            dumps(compatibility or []),
            dumps(lineage_gaps or []),
            dumps(evidence_ids or []),
            dumps(warnings or []),
            dumps(errors or []),
            dumps(details or {}),
            idempotency_key,
            utc_now_iso(),
        ),
    )
    return get_assessment(conn, assessment_id)  # type: ignore[return-value]


def get_assessment(
    conn: sqlite3.Connection, assessment_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM recovery_assessments WHERE recovery_assessment_id = ?",
        (assessment_id,),
    ).fetchone()
    return row_to_dict(row, json_fields=_ASSESSMENT_JSON_FIELDS)


def get_assessment_by_idempotency(
    conn: sqlite3.Connection, idempotency_key: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM recovery_assessments WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    return row_to_dict(row, json_fields=_ASSESSMENT_JSON_FIELDS)


def create_recovery(
    conn: sqlite3.Connection,
    *,
    incident_id: str,
    recovery_status: str,
    recovery_strategy: str,
    assessment_id: str | None = None,
    recovery_reason: str | None = None,
    source_checkpoint_id: str | None = None,
    recovery_artifact_id: str | None = None,
    recovered_checkpoint_id: str | None = None,
    target_environment_version: str | None = None,
    target_agent_config_fingerprint: str | None = None,
    recovery_started_at: str | None = None,
    recovery_completed_at: str | None = None,
    proposed_actions: list[dict[str, Any]] | None = None,
    executed_actions: list[dict[str, Any]] | None = None,
    preflight: dict[str, Any] | None = None,
    failure_reason: str | None = None,
    evidence_ids: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    details: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    recovery_id = new_id("recovery")
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO recoveries(
            recovery_id, incident_id, assessment_id, recovery_status,
            recovery_strategy, recovery_reason, source_checkpoint_id,
            recovery_artifact_id, recovered_checkpoint_id,
            target_environment_version, target_agent_config_fingerprint,
            recovery_started_at, recovery_completed_at, proposed_actions_json,
            executed_actions_json, preflight_json, failure_reason,
            evidence_ids_json, warnings_json, errors_json, details_json,
            idempotency_key, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            recovery_id,
            incident_id,
            assessment_id,
            recovery_status,
            recovery_strategy,
            recovery_reason,
            source_checkpoint_id,
            recovery_artifact_id,
            recovered_checkpoint_id,
            target_environment_version,
            target_agent_config_fingerprint,
            recovery_started_at,
            recovery_completed_at,
            dumps(proposed_actions or []),
            dumps(executed_actions or []),
            dumps(preflight or {}),
            failure_reason,
            dumps(evidence_ids or []),
            dumps(warnings or []),
            dumps(errors or []),
            dumps(details or {}),
            idempotency_key,
            now,
            now,
        ),
    )
    return get_recovery(conn, recovery_id)  # type: ignore[return-value]


def get_recovery(
    conn: sqlite3.Connection, recovery_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM recoveries WHERE recovery_id = ?", (recovery_id,)
    ).fetchone()
    return row_to_dict(row, json_fields=_RECOVERY_JSON_FIELDS)


def get_recovery_by_idempotency(
    conn: sqlite3.Connection, idempotency_key: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM recoveries WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    return row_to_dict(row, json_fields=_RECOVERY_JSON_FIELDS)


def list_recoveries_for_incident(
    conn: sqlite3.Connection, incident_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM recoveries WHERE incident_id = ? ORDER BY created_at",
        (incident_id,),
    ).fetchall()
    return [row_to_dict(row, json_fields=_RECOVERY_JSON_FIELDS) for row in rows]  # type: ignore[misc]


_UPDATABLE_RECOVERY_COLUMNS = {
    "recovery_status",
    "recovery_reason",
    "source_checkpoint_id",
    "recovery_artifact_id",
    "recovered_checkpoint_id",
    "target_environment_version",
    "target_agent_config_fingerprint",
    "recovery_started_at",
    "recovery_completed_at",
    "proposed_actions_json",
    "executed_actions_json",
    "preflight_json",
    "failure_reason",
    "evidence_ids_json",
    "warnings_json",
    "errors_json",
    "details_json",
}


def update_recovery(
    conn: sqlite3.Connection, recovery_id: str, **fields: Any
) -> dict[str, Any]:
    assignments: list[str] = []
    values: list[Any] = []
    for key, value in fields.items():
        if key not in _UPDATABLE_RECOVERY_COLUMNS:
            raise ValueError(f"Unsupported recovery field: {key}")
        assignments.append(f"{key} = ?")
        values.append(value)
    assignments.append("updated_at = ?")
    values.append(utc_now_iso())
    values.append(recovery_id)
    conn.execute(
        f"UPDATE recoveries SET {', '.join(assignments)} WHERE recovery_id = ?",
        values,
    )
    return get_recovery(conn, recovery_id)  # type: ignore[return-value]
