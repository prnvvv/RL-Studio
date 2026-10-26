from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ..utils import dumps, new_id, utc_now_iso
from ._common import row_to_dict


_JSON_FIELDS = {
    "affected_artifact_ids_json": "affected_artifact_ids",
    "affected_trajectory_ids_json": "affected_trajectory_ids",
    "affected_policy_update_ids_json": "affected_policy_update_ids",
    "affected_checkpoint_ids_json": "affected_checkpoint_ids",
    "evidence_ids_json": "evidence_ids",
    "warnings_json": "warnings",
    "errors_json": "errors",
    "details_json": "details",
}


def create_impact(
    conn: sqlite3.Connection,
    *,
    incident_id: str,
    run_id: str,
    impact_status: str,
    source_environment_version: Optional[str] = None,
    corruption_start_timestep: Optional[int] = None,
    corruption_end_timestep: Optional[int] = None,
    impact_score: Optional[float] = None,
    affected_artifact_ids: Optional[list[str]] = None,
    affected_trajectory_ids: Optional[list[str]] = None,
    affected_policy_update_ids: Optional[list[str]] = None,
    affected_checkpoint_ids: Optional[list[str]] = None,
    evidence_ids: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
    errors: Optional[list[str]] = None,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    impact_id = new_id("impact")
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO impact_analyses(
            impact_id, incident_id, run_id, impact_status, impact_score,
            source_environment_version, corruption_start_timestep,
            corruption_end_timestep, affected_artifact_ids_json,
            affected_trajectory_ids_json, affected_policy_update_ids_json,
            affected_checkpoint_ids_json, evidence_ids_json, warnings_json,
            errors_json, details_json, created_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            impact_id,
            incident_id,
            run_id,
            impact_status,
            impact_score,
            source_environment_version,
            corruption_start_timestep,
            corruption_end_timestep,
            dumps(affected_artifact_ids or []),
            dumps(affected_trajectory_ids or []),
            dumps(affected_policy_update_ids or []),
            dumps(affected_checkpoint_ids or []),
            dumps(evidence_ids or []),
            dumps(warnings or []),
            dumps(errors or []),
            dumps(details or {}),
            now,
            now,
        ),
    )
    return get_impact(conn, impact_id)  # type: ignore[return-value]


def get_impact(
    conn: sqlite3.Connection, impact_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM impact_analyses WHERE impact_id = ?", (impact_id,)
    ).fetchone()
    return row_to_dict(row, json_fields=_JSON_FIELDS)


def get_latest_impact_for_incident(
    conn: sqlite3.Connection, incident_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT * FROM impact_analyses
        WHERE incident_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (incident_id,),
    ).fetchone()
    return row_to_dict(row, json_fields=_JSON_FIELDS)


def list_impacts_for_incident(
    conn: sqlite3.Connection, incident_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM impact_analyses WHERE incident_id = ? ORDER BY created_at",
        (incident_id,),
    ).fetchall()
    return [row_to_dict(row, json_fields=_JSON_FIELDS) for row in rows]  # type: ignore[misc]
