from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ..utils import dumps, new_id, utc_now_iso
from ._common import row_to_dict


_JSON_FIELDS = {
    "included_state_components_json": "included_state_components",
    "metadata_json": "metadata",
}


def create_artifact(
    conn: sqlite3.Connection,
    *,
    artifact_id: str,
    run_id: str,
    artifact_type: str,
    artifact_path: str,
    artifact_status: str,
    integrity_status: str,
    artifact_hash: Optional[str] = None,
    artifact_version: Optional[str] = None,
    artifact_created_at: Optional[str] = None,
    parent_artifact_id: Optional[str] = None,
    checkpoint_id: Optional[str] = None,
    checkpoint_path: Optional[str] = None,
    policy_version: Optional[str] = None,
    trajectory_id: Optional[str] = None,
    experience_id: Optional[str] = None,
    policy_update_id: Optional[str] = None,
    environment_id: Optional[str] = None,
    environment_version: Optional[str] = None,
    agent_config_fingerprint: Optional[str] = None,
    episode_id: Optional[str] = None,
    timestep: Optional[int] = None,
    update_index: Optional[int] = None,
    included_state_components: Optional[list[str]] = None,
    metadata_schema_version: str = "1.0",
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO artifacts(
            artifact_id, run_id, artifact_type, artifact_path, artifact_hash,
            artifact_version, artifact_status, artifact_created_at,
            parent_artifact_id, checkpoint_id, checkpoint_path, policy_version,
            trajectory_id, experience_id, policy_update_id, environment_id,
            environment_version, agent_config_fingerprint, episode_id, timestep,
            update_index, included_state_components_json, integrity_status,
            metadata_schema_version, metadata_json, created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?
        )
        """,
        (
            artifact_id,
            run_id,
            artifact_type,
            artifact_path,
            artifact_hash,
            artifact_version,
            artifact_status,
            artifact_created_at or now,
            parent_artifact_id,
            checkpoint_id,
            checkpoint_path,
            policy_version,
            trajectory_id,
            experience_id,
            policy_update_id,
            environment_id,
            environment_version,
            agent_config_fingerprint,
            episode_id,
            timestep,
            update_index,
            dumps(included_state_components or []),
            integrity_status,
            metadata_schema_version,
            dumps(metadata or {}),
            now,
            now,
        ),
    )
    return get_artifact(conn, artifact_id)  # type: ignore[return-value]


def get_artifact(conn: sqlite3.Connection, artifact_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)
    ).fetchone()
    return row_to_dict(row, json_fields=_JSON_FIELDS)


def get_artifact_by_checkpoint_id(
    conn: sqlite3.Connection, checkpoint_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM artifacts WHERE checkpoint_id = ? ORDER BY created_at DESC LIMIT 1",
        (checkpoint_id,),
    ).fetchone()
    return row_to_dict(row, json_fields=_JSON_FIELDS)


def list_artifacts_for_run(
    conn: sqlite3.Connection, run_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM artifacts
        WHERE run_id = ?
        ORDER BY COALESCE(timestep, 0), COALESCE(update_index, 0), created_at
        """,
        (run_id,),
    ).fetchall()
    return [row_to_dict(row, json_fields=_JSON_FIELDS) for row in rows]  # type: ignore[misc]


def update_artifact_status(
    conn: sqlite3.Connection,
    artifact_id: str,
    *,
    artifact_status: str,
    integrity_status: str | None = None,
) -> None:
    if integrity_status is None:
        conn.execute(
            "UPDATE artifacts SET artifact_status = ?, updated_at = ? WHERE artifact_id = ?",
            (artifact_status, utc_now_iso(), artifact_id),
        )
    else:
        conn.execute(
            """
            UPDATE artifacts
            SET artifact_status = ?, integrity_status = ?, updated_at = ?
            WHERE artifact_id = ?
            """,
            (artifact_status, integrity_status, utc_now_iso(), artifact_id),
        )


def create_link(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    from_artifact_id: str,
    to_artifact_id: str,
    relation: str,
) -> dict[str, Any]:
    link_id = new_id("link")
    conn.execute(
        """
        INSERT OR IGNORE INTO artifact_links(
            link_id, run_id, from_artifact_id, to_artifact_id, relation, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (link_id, run_id, from_artifact_id, to_artifact_id, relation, utc_now_iso()),
    )
    row = conn.execute(
        """
        SELECT * FROM artifact_links
        WHERE from_artifact_id = ? AND to_artifact_id = ? AND relation = ?
        """,
        (from_artifact_id, to_artifact_id, relation),
    ).fetchone()
    return dict(row)  # type: ignore[arg-type]


def list_links_for_run(conn: sqlite3.Connection, run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM artifact_links WHERE run_id = ? ORDER BY created_at",
        (run_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_links_for_artifact(
    conn: sqlite3.Connection, artifact_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM artifact_links
        WHERE from_artifact_id = ? OR to_artifact_id = ?
        ORDER BY created_at
        """,
        (artifact_id, artifact_id),
    ).fetchall()
    return [dict(row) for row in rows]
