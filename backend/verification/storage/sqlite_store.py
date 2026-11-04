"""Durable verification persistence on the shared SQLite ``Database`` (no second database).

Tables come from forward migration 2 in ``backend/database/migrations.py``. Records survive a
backend restart: nothing here keeps state in memory. Verifications and their per-requirement
results are append-only; a requirement row only moves along its lifecycle.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.database.connection import Database
from backend.database.utils import dumps, loads, utc_now_iso


def _row(row: sqlite3.Row | None, json_cols: dict[str, tuple[str, Any]]) -> dict[str, Any] | None:
    if row is None:
        return None
    rec = dict(row)
    for col, (key, default) in json_cols.items():
        rec[key] = loads(rec.pop(col, None), default)
    return rec


_INTENT_JSON = {
    "context_json": ("context", {}),
    "interpretation_json": ("interpretation", {}),
    "ai_json": ("ai", {}),
    "source_refs_json": ("source_refs", {}),
}
_REQ_JSON = {
    "expected_value_json": ("expected_value", None),
    "evidence_required_json": ("evidence_required", []),
    "validation_json": ("validation", {}),
    "requirement_json": ("requirement", {}),
}
_VERIFICATION_JSON = {
    "requirement_ids_json": ("requirement_ids", []),
    "traceability_json": ("traceability", {}),
    "output_json": ("output", {}),
}
_RESULT_JSON = {
    "expected_json": ("expected", None),
    "actual_json": ("actual", None),
    "evidence_refs_json": ("evidence_refs", []),
    "details_json": ("details", {}),
}
_LINK_JSON = {"failed_requirement_ids_json": ("failed_requirement_ids", [])}


class SqliteVerificationStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    # ---- intents ---------------------------------------------------------------------------
    def save_intent(self, rec: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        with self.database.write() as conn:
            conn.execute(
                """INSERT INTO verification_intents(intent_id, run_id, environment_id, environment_version,
                   original_text, context_json, status, status_reason, interpretation_json, ai_json,
                   source_refs_json, idempotency_key, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rec["intent_id"], rec["run_id"], rec.get("environment_id"), rec.get("environment_version"),
                 rec["original_text"], dumps(rec.get("context") or {}), rec["status"], rec.get("status_reason"),
                 dumps(rec.get("interpretation") or {}), dumps(rec.get("ai") or {}),
                 dumps(rec.get("source_refs") or {}), rec["idempotency_key"], now, now),
            )
        return self.get_intent(rec["intent_id"])  # type: ignore[return-value]

    def update_intent(self, intent_id: str, **fields: Any) -> None:
        json_map = {"interpretation": "interpretation_json", "ai": "ai_json", "source_refs": "source_refs_json",
                    "context": "context_json"}
        sets, args = ["updated_at = ?"], [utc_now_iso()]
        for key, value in fields.items():
            if key in json_map:
                sets.append(f"{json_map[key]} = ?")
                args.append(dumps(value))
            elif key in {"status", "status_reason", "environment_version", "environment_id"}:
                sets.append(f"{key} = ?")
                args.append(value)
            else:
                raise ValueError(f"unsupported intent field {key!r}")
        with self.database.write() as conn:
            conn.execute(f"UPDATE verification_intents SET {', '.join(sets)} WHERE intent_id = ?", (*args, intent_id))

    def get_intent(self, intent_id: str) -> dict[str, Any] | None:
        with self.database.read() as conn:
            row = conn.execute("SELECT * FROM verification_intents WHERE intent_id = ?", (intent_id,)).fetchone()
        return _row(row, _INTENT_JSON)

    def find_intent_by_key(self, key: str, run_id: str, statuses: tuple[str, ...]) -> dict[str, Any] | None:
        marks = ",".join("?" for _ in statuses)
        with self.database.read() as conn:
            row = conn.execute(
                f"SELECT * FROM verification_intents WHERE idempotency_key = ? AND run_id = ? "
                f"AND status IN ({marks}) ORDER BY rowid DESC LIMIT 1",
                (key, run_id, *statuses),
            ).fetchone()
        return _row(row, _INTENT_JSON)

    def list_intents(self, run_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute(
                "SELECT * FROM verification_intents WHERE run_id = ? ORDER BY rowid", (run_id,)
            ).fetchall()
        return [_row(r, _INTENT_JSON) for r in rows]  # type: ignore[misc]

    # ---- requirements -----------------------------------------------------------------------
    def save_requirement(self, rec: dict[str, Any]) -> None:
        now = utc_now_iso()
        with self.database.write() as conn:
            conn.execute(
                """INSERT INTO verification_requirements(requirement_id, intent_id, run_id, environment_id,
                   environment_version, category, source_statement, description, criterion, comparison_operator,
                   expected_value_json, tolerance, evidence_required_json, lifecycle_status, validation_status,
                   validation_json, requirement_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rec["requirement_id"], rec["intent_id"], rec["run_id"], rec.get("environment_id"),
                 rec.get("environment_version"), rec["category"], rec["source_statement"], rec["description"],
                 rec.get("criterion"), rec.get("comparison_operator"), dumps(rec.get("expected_value")),
                 rec.get("tolerance"), dumps(rec.get("evidence_required") or []), rec["lifecycle_status"],
                 rec["validation_status"], dumps(rec.get("validation") or {}), dumps(rec["requirement"]), now, now),
            )

    def update_requirement(self, requirement_id: str, **fields: Any) -> None:
        json_map = {"expected_value": "expected_value_json", "evidence_required": "evidence_required_json",
                    "validation": "validation_json", "requirement": "requirement_json"}
        plain = {"description", "criterion", "comparison_operator", "tolerance", "lifecycle_status",
                 "validation_status", "environment_version", "last_verification_id", "last_result_status",
                 "confirmed_at"}
        sets, args = ["updated_at = ?"], [utc_now_iso()]
        for key, value in fields.items():
            if key in json_map:
                sets.append(f"{json_map[key]} = ?")
                args.append(dumps(value))
            elif key in plain:
                sets.append(f"{key} = ?")
                args.append(value)
            else:
                raise ValueError(f"unsupported requirement field {key!r}")
        with self.database.write() as conn:
            conn.execute(
                f"UPDATE verification_requirements SET {', '.join(sets)} WHERE requirement_id = ?",
                (*args, requirement_id),
            )

    def get_requirement(self, requirement_id: str) -> dict[str, Any] | None:
        with self.database.read() as conn:
            row = conn.execute(
                "SELECT * FROM verification_requirements WHERE requirement_id = ?", (requirement_id,)
            ).fetchone()
        return _row(row, _REQ_JSON)

    def list_requirements(self, *, intent_id: str | None = None, run_id: str | None = None) -> list[dict[str, Any]]:
        where, args = ("intent_id = ?", intent_id) if intent_id else ("run_id = ?", run_id)
        with self.database.read() as conn:
            rows = conn.execute(
                f"SELECT * FROM verification_requirements WHERE {where} ORDER BY rowid", (args,)
            ).fetchall()
        return [_row(r, _REQ_JSON) for r in rows]  # type: ignore[misc]

    # ---- verifications ----------------------------------------------------------------------
    def save_verification(self, rec: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
        """Atomically persist a verification with every requirement-level result and mark the
        requirements. Idempotent on ``idempotency_key`` (the existing record is returned)."""
        now = utc_now_iso()
        with self.database.write() as conn:
            existing = conn.execute(
                "SELECT verification_id FROM verifications WHERE idempotency_key = ?", (rec["idempotency_key"],)
            ).fetchone()
            if existing is not None:
                return self._load_verification(conn, existing["verification_id"])  # type: ignore[return-value]
            conn.execute(
                """INSERT INTO verifications(verification_id, run_id, intent_id, environment_id,
                   environment_version, overall_status, contract_status, idempotency_key, requirement_ids_json,
                   traceability_json, output_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (rec["verification_id"], rec["run_id"], rec.get("intent_id"), rec.get("environment_id"),
                 rec.get("environment_version"), rec["overall_status"], rec.get("contract_status"),
                 rec["idempotency_key"], dumps(rec["requirement_ids"]), dumps(rec.get("traceability") or {}),
                 dumps(rec["output"]), now),
            )
            for r in results:
                conn.execute(
                    """INSERT INTO verification_results(verification_id, requirement_id, status, contract_status,
                       expected_json, actual_json, tolerance, evidence_refs_json, details_json, is_mandatory,
                       created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (rec["verification_id"], r["requirement_id"], r["status"], r.get("contract_status"),
                     dumps(r.get("expected")), dumps(r.get("actual")), r.get("tolerance"),
                     dumps(r.get("evidence_refs") or []), dumps(r.get("details") or {}),
                     int(bool(r.get("is_mandatory", True))), now),
                )
                lifecycle = {"pass": "verified", "fail": "failed", "blocked": "invalid"}.get(r["status"], "unknown")
                conn.execute(
                    """UPDATE verification_requirements SET lifecycle_status = ?, last_verification_id = ?,
                       last_result_status = ?, updated_at = ? WHERE requirement_id = ?""",
                    (lifecycle, rec["verification_id"], r["status"], now, r["requirement_id"]),
                )
            return self._load_verification(conn, rec["verification_id"])  # type: ignore[return-value]

    @staticmethod
    def _load_verification(conn: sqlite3.Connection, verification_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM verifications WHERE verification_id = ?", (verification_id,)).fetchone()
        return _row(row, _VERIFICATION_JSON)

    def get_verification(self, verification_id: str) -> dict[str, Any] | None:
        with self.database.read() as conn:
            return self._load_verification(conn, verification_id)

    def find_verification_by_key(self, key: str) -> dict[str, Any] | None:
        with self.database.read() as conn:
            row = conn.execute("SELECT * FROM verifications WHERE idempotency_key = ?", (key,)).fetchone()
        return _row(row, _VERIFICATION_JSON)

    def list_verifications(self, run_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute(
                "SELECT * FROM verifications WHERE run_id = ? ORDER BY rowid", (run_id,)
            ).fetchall()
        return [_row(r, _VERIFICATION_JSON) for r in rows]  # type: ignore[misc]

    def get_results(self, verification_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute(
                "SELECT * FROM verification_results WHERE verification_id = ? ORDER BY requirement_id",
                (verification_id,),
            ).fetchall()
        out = [_row(r, _RESULT_JSON) for r in rows]
        for rec in out:
            rec["is_mandatory"] = bool(rec["is_mandatory"])  # type: ignore[index]
        return out  # type: ignore[return-value]

    # ---- incident association ----------------------------------------------------------------
    def upsert_link(
        self, verification_id: str, run_id: str, *, handoff_status: str, incident_id: str | None = None,
        failed_requirement_ids: list[str] | None = None, error_code: str | None = None, attempt: bool = False,
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self.database.write() as conn:
            conn.execute(
                """INSERT INTO verification_incident_links(verification_id, run_id, incident_id, handoff_status,
                   failed_requirement_ids_json, error_code, attempts, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(verification_id) DO UPDATE SET
                     incident_id = COALESCE(excluded.incident_id, verification_incident_links.incident_id),
                     handoff_status = excluded.handoff_status,
                     failed_requirement_ids_json = excluded.failed_requirement_ids_json,
                     error_code = excluded.error_code,
                     attempts = verification_incident_links.attempts + ?,
                     updated_at = excluded.updated_at""",
                (verification_id, run_id, incident_id, handoff_status, dumps(failed_requirement_ids or []),
                 error_code, 1 if attempt else 0, now, now, 1 if attempt else 0),
            )
        return self.get_link(verification_id)  # type: ignore[return-value]

    def get_link(self, verification_id: str) -> dict[str, Any] | None:
        with self.database.read() as conn:
            row = conn.execute(
                "SELECT * FROM verification_incident_links WHERE verification_id = ?", (verification_id,)
            ).fetchone()
        return _row(row, _LINK_JSON)


__all__ = ["SqliteVerificationStore"]
