"""Persistence for advisory investigations (``incident_investigations``, migration 5).

Rows are append-only: a new investigation is a new row, an existing row is never updated or deleted, so earlier
advisory output stays auditable. A row stores the exact evidence index the model was allowed to cite, the grounded
result, and which model produced it.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from backend.database.connection import Database
from backend.database.utils import utc_now_iso

_COLUMNS = ("investigation_id", "incident_id", "run_id", "kind", "status", "context_hash",
            "based_on_investigation_id", "evidence_index_json", "result_json", "ai_json", "warnings_json", "created_at")


def _row(row: Any) -> dict[str, Any]:
    rec = dict(row)
    return {
        "investigation_id": rec["investigation_id"], "incident_id": rec["incident_id"], "run_id": rec["run_id"],
        "kind": rec["kind"], "status": rec["status"], "context_hash": rec["context_hash"],
        "based_on_investigation_id": rec["based_on_investigation_id"],
        "evidence_index": json.loads(rec["evidence_index_json"]), "result": json.loads(rec["result_json"]),
        "ai": json.loads(rec["ai_json"]), "warnings": json.loads(rec["warnings_json"]),
        "created_at": rec["created_at"],
    }


class InvestigationStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, *, incident_id: str, run_id: str, kind: str, status: str, context_hash: str,
             evidence_index: dict[str, str], result: dict[str, Any], ai: dict[str, Any],
             warnings: list[str], based_on: str | None = None) -> dict[str, Any]:
        investigation_id = f"inv-{uuid.uuid4().hex[:16]}"
        with self.database.write() as conn:
            conn.execute(
                f"INSERT INTO incident_investigations({', '.join(_COLUMNS)}) VALUES ({', '.join('?' * len(_COLUMNS))})",
                (investigation_id, incident_id, run_id, kind, status, context_hash, based_on,
                 json.dumps(evidence_index, sort_keys=True), json.dumps(result, default=str),
                 json.dumps(ai, default=str), json.dumps(warnings), utc_now_iso()))
        saved = self.get(investigation_id)
        assert saved is not None
        return saved

    def get(self, investigation_id: str) -> dict[str, Any] | None:
        with self.database.read() as conn:
            row = conn.execute("SELECT * FROM incident_investigations WHERE investigation_id = ?",
                               (investigation_id,)).fetchone()
        return _row(row) if row else None

    def list_for_incident(self, incident_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM incident_investigations WHERE incident_id = ?"
        args: list[Any] = [incident_id]
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        with self.database.read() as conn:
            rows = conn.execute(sql + " ORDER BY created_at, rowid", args).fetchall()
        return [_row(r) for r in rows]

    def latest(self, incident_id: str, kind: str, *, context_hash: str | None = None,
               statuses: tuple[str, ...] = ("completed",)) -> dict[str, Any] | None:
        for rec in reversed(self.list_for_incident(incident_id, kind)):
            if rec["status"] in statuses and (context_hash is None or rec["context_hash"] == context_hash):
                return rec
        return None
