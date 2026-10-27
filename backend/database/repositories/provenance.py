from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ..utils import dumps, new_id, utc_now_iso
from ._common import row_to_dict
from . import runs as runs_repo


_JSON_FIELDS = {
    "warnings_json": "warnings",
    "evidence_ids_json": "evidence_ids",
    "details_json": "details",
}


def upsert_provenance_record(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    provenance_status: str,
    lineage_completeness: str,
    source_environment_version: Optional[str],
    artifact_count: int,
    warnings: Optional[list[str]] = None,
    evidence_ids: Optional[list[str]] = None,
    details: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    existing = conn.execute(
        "SELECT provenance_id, created_at FROM provenance_records WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if existing is None:
        provenance_id = new_id("prov")
        conn.execute(
            """
            INSERT INTO provenance_records(
                provenance_id, run_id, provenance_status, lineage_completeness,
                source_environment_version, artifact_count, warnings_json,
                evidence_ids_json, details_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provenance_id,
                run_id,
                provenance_status,
                lineage_completeness,
                source_environment_version,
                artifact_count,
                dumps(warnings or []),
                dumps(evidence_ids or []),
                dumps(details or {}),
                now,
                now,
            ),
        )
    else:
        provenance_id = existing["provenance_id"]
        conn.execute(
            """
            UPDATE provenance_records SET
                provenance_status = ?,
                lineage_completeness = ?,
                source_environment_version = ?,
                artifact_count = ?,
                warnings_json = ?,
                evidence_ids_json = ?,
                details_json = ?,
                updated_at = ?
            WHERE run_id = ?
            """,
            (
                provenance_status,
                lineage_completeness,
                source_environment_version,
                artifact_count,
                dumps(warnings or []),
                dumps(evidence_ids or []),
                dumps(details or {}),
                now,
                run_id,
            ),
        )
    return get_provenance_for_run(conn, run_id)  # type: ignore[return-value]


def get_provenance_for_run(
    conn: sqlite3.Connection, run_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM provenance_records WHERE run_id = ?", (run_id,)
    ).fetchone()
    return row_to_dict(row, json_fields=_JSON_FIELDS)


def run_exists(conn: sqlite3.Connection, run_id: str) -> bool:
    return runs_repo.get_run(conn, run_id) is not None
