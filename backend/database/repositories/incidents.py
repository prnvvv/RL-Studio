from __future__ import annotations

import sqlite3
from typing import Any

from ..utils import dumps, utc_now_iso
from ._common import row_to_dict

_JSON_FIELDS = {
    "evidence_ids_json": "evidence_ids",
    "details_json": "details",
}


def create_incident(
    conn: sqlite3.Connection,
    *,
    incident_id: str,
    run_id: str,
    status: str,
    verification_id: str | None = None,
    environment_id: str | None = None,
    environment_version: str | None = None,
    requirement_id: str | None = None,
    severity: str | None = None,
    detection_method: str | None = None,
    summary: str | None = None,
    evidence_ids: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO incidents(
            incident_id, run_id, verification_id, environment_id,
            environment_version, requirement_id, status, severity,
            detection_method, summary, evidence_ids_json, details_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            incident_id,
            run_id,
            verification_id,
            environment_id,
            environment_version,
            requirement_id,
            status,
            severity,
            detection_method,
            summary,
            dumps(evidence_ids or []),
            dumps(details or {}),
            now,
            now,
        ),
    )
    return get_incident(conn, incident_id)  # type: ignore[return-value]


def get_incident(conn: sqlite3.Connection, incident_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
    ).fetchone()
    return row_to_dict(row, json_fields=_JSON_FIELDS)


def list_incidents_for_run(
    conn: sqlite3.Connection, run_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM incidents WHERE run_id = ? ORDER BY created_at DESC",
        (run_id,),
    ).fetchall()
    return [row_to_dict(row, json_fields=_JSON_FIELDS) for row in rows]  # type: ignore[misc]


def set_incident_fault(
    conn: sqlite3.Connection,
    *,
    incident_id: str,
    source_environment_version: str | None = None,
    corruption_start_timestep: int | None = None,
    corruption_end_timestep: int | None = None,
    fault_type: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO incident_faults(
            incident_id, source_environment_version,
            corruption_start_timestep, corruption_end_timestep,
            fault_type, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(incident_id) DO UPDATE SET
            source_environment_version = excluded.source_environment_version,
            corruption_start_timestep = excluded.corruption_start_timestep,
            corruption_end_timestep = excluded.corruption_end_timestep,
            fault_type = excluded.fault_type
        """,
        (
            incident_id,
            source_environment_version,
            corruption_start_timestep,
            corruption_end_timestep,
            fault_type,
            utc_now_iso(),
        ),
    )


def get_incident_fault(
    conn: sqlite3.Connection, incident_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM incident_faults WHERE incident_id = ?", (incident_id,)
    ).fetchone()
    return dict(row) if row is not None else None
