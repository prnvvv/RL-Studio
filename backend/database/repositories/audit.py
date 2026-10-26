from __future__ import annotations

import sqlite3
from typing import Any, Optional

from ..utils import dumps, new_id, utc_now_iso
from ._common import row_to_dict


_JSON_FIELDS = {"details_json": "details"}


def append_audit(
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    status: str,
    actor: Optional[str] = None,
    correlation_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> str:
    audit_id = new_id("audit")
    conn.execute(
        """
        INSERT INTO audit_events(
            audit_id, entity_type, entity_id, action, status, actor,
            correlation_id, details_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            audit_id,
            entity_type,
            entity_id,
            action,
            status,
            actor,
            correlation_id,
            dumps(details or {}),
            utc_now_iso(),
        ),
    )
    return audit_id


def list_audit(
    conn: sqlite3.Connection,
    *,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    values: list[Any] = []
    if entity_type is not None:
        clauses.append("entity_type = ?")
        values.append(entity_type)
    if entity_id is not None:
        clauses.append("entity_id = ?")
        values.append(entity_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM audit_events {where} ORDER BY created_at, audit_id",
        values,
    ).fetchall()
    return [row_to_dict(row, json_fields=_JSON_FIELDS) for row in rows]  # type: ignore[misc]
