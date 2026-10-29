from __future__ import annotations

import sqlite3
from typing import Any

from ..utils import dumps, utc_now_iso
from ._common import row_to_dict

_JSON_FIELDS = {"metadata_json": "metadata"}


def create_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    project_id: str | None = None,
    experiment_id: str | None = None,
    environment_id: str | None = None,
    environment_version: str | None = None,
    agent_config_fingerprint: str | None = None,
    status: str = "created",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO runs(
            run_id, project_id, experiment_id, environment_id,
            environment_version, agent_config_fingerprint, status,
            metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            project_id,
            experiment_id,
            environment_id,
            environment_version,
            agent_config_fingerprint,
            status,
            dumps(metadata or {}),
            now,
            now,
        ),
    )
    return get_run(conn, run_id)  # type: ignore[return-value]


def get_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return row_to_dict(row, json_fields=_JSON_FIELDS)


def list_runs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
    return [row_to_dict(row, json_fields=_JSON_FIELDS) for row in rows]  # type: ignore[misc]


def update_run_status(conn: sqlite3.Connection, run_id: str, status: str) -> None:
    conn.execute(
        "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
        (status, utc_now_iso(), run_id),
    )
