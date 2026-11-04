"""SQL for the project tables (migration 3) and the project-owned columns of ``runs``.

Only project data is written here. Runs, events, incidents and verification records are never deleted or
rewritten; the single write to ``runs`` is the explicit, one-time legacy adoption of a run that has no project.
"""

from __future__ import annotations

from typing import Any

from backend.database.connection import Database
from backend.database.utils import dumps, loads, utc_now_iso

ACTIVE_RUN_STATUSES = ("created", "running", "paused", "resuming")


def _project(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    rec = dict(row)
    rec["agent"] = loads(rec.pop("agent_json", None), {})
    rec["environment"] = loads(rec.pop("environment_json", None), {})
    return rec


class ProjectRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    # ---- projects ----------------------------------------------------------------------------------
    def insert_project(self, project_id: str, name: str, description: str | None, agent: dict[str, Any],
                       environment: dict[str, Any]) -> dict[str, Any]:
        now = utc_now_iso()
        with self.database.write() as conn:
            conn.execute(
                "INSERT INTO projects(project_id, name, description, status, agent_json, environment_json, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (project_id, name, description, "active", dumps(agent), dumps(environment), now, now),
            )
        return self.get_project(project_id)  # type: ignore[return-value]

    def get_project(self, project_id: str, *, include_deleted: bool = False) -> dict[str, Any] | None:
        sql = "SELECT * FROM projects WHERE project_id = ?" + ("" if include_deleted else " AND status = 'active'")
        with self.database.read() as conn:
            return _project(conn.execute(sql, (project_id,)).fetchone())

    def list_projects(self) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute("SELECT * FROM projects WHERE status = 'active' ORDER BY updated_at DESC, rowid DESC").fetchall()
        return [_project(r) for r in rows]  # type: ignore[misc]

    def update_project(self, project_id: str, **fields: Any) -> None:
        mapping = {"name": "name", "description": "description", "agent": "agent_json", "environment": "environment_json"}
        sets, args = ["updated_at = ?"], [utc_now_iso()]
        for key, value in fields.items():
            sets.append(f"{mapping[key]} = ?")
            args.append(dumps(value) if key in ("agent", "environment") else value)
        with self.database.write() as conn:
            conn.execute(f"UPDATE projects SET {', '.join(sets)} WHERE project_id = ? AND status = 'active'", (*args, project_id))

    def touch(self, project_id: str) -> None:
        with self.database.write() as conn:
            conn.execute("UPDATE projects SET updated_at = ? WHERE project_id = ?", (utc_now_iso(), project_id))

    def soft_delete(self, project_id: str) -> None:
        now = utc_now_iso()
        with self.database.write() as conn:
            conn.execute("UPDATE projects SET status = 'deleted', deleted_at = ?, updated_at = ? WHERE project_id = ?",
                         (now, now, project_id))

    # ---- runs (association lives in ``runs.project_id``) ----------------------------------------------
    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.database.read() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return None if row is None else dict(row)

    def project_runs(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute("SELECT * FROM runs WHERE project_id = ? ORDER BY created_at DESC, rowid DESC", (project_id,)).fetchall()
        return [dict(r) for r in rows]

    def legacy_runs(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute("SELECT * FROM runs WHERE project_id IS NULL ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def adopt_run(self, project_id: str, run_id: str) -> bool:
        """Associate a run that has no project. Never reassigns a run that already belongs to one."""
        with self.database.write() as conn:
            cur = conn.execute("UPDATE runs SET project_id = ?, updated_at = ? WHERE run_id = ? AND project_id IS NULL",
                               (project_id, utc_now_iso(), run_id))
            return cur.rowcount == 1

    # ---- documents -------------------------------------------------------------------------------------
    def insert_document(self, rec: dict[str, Any]) -> None:
        with self.database.write() as conn:
            conn.execute(
                "INSERT INTO project_documents(document_id, project_id, filename, content_type, size_bytes, sha256, "
                "storage_reference, extraction_status, extraction_error, extracted_text, text_chars, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (rec["document_id"], rec["project_id"], rec["filename"], rec["content_type"], rec["size_bytes"],
                 rec["sha256"], rec["storage_reference"], rec["extraction_status"], rec.get("extraction_error"),
                 rec.get("extracted_text"), rec.get("text_chars", 0), utc_now_iso()),
            )

    def get_document(self, project_id: str, document_id: str) -> dict[str, Any] | None:
        with self.database.read() as conn:
            row = conn.execute("SELECT * FROM project_documents WHERE project_id = ? AND document_id = ?",
                               (project_id, document_id)).fetchone()
        return None if row is None else dict(row)

    def find_document_by_hash(self, project_id: str, sha256: str) -> dict[str, Any] | None:
        with self.database.read() as conn:
            row = conn.execute("SELECT * FROM project_documents WHERE project_id = ? AND sha256 = ? ORDER BY rowid LIMIT 1",
                               (project_id, sha256)).fetchone()
        return None if row is None else dict(row)

    def list_documents(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute("SELECT * FROM project_documents WHERE project_id = ? ORDER BY rowid", (project_id,)).fetchall()
        return [dict(r) for r in rows]

    # ---- intent / requirement links ----------------------------------------------------------------------
    def link_intent(self, intent_id: str, project_id: str, stage: str, run_id: str | None,
                    document_ids: list[str], source: dict[str, Any]) -> None:
        with self.database.write() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO project_intent_links(intent_id, project_id, stage, run_id, document_ids_json, "
                "source_json, created_at) VALUES (?,?,?,?,?,?,?)",
                (intent_id, project_id, stage, run_id, dumps(document_ids), dumps(source), utc_now_iso()),
            )

    def intent_links(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute("SELECT * FROM project_intent_links WHERE project_id = ? ORDER BY rowid", (project_id,)).fetchall()
        out = []
        for r in rows:
            rec = dict(r)
            rec["document_ids"] = loads(rec.pop("document_ids_json"), [])
            rec["source"] = loads(rec.pop("source_json"), {})
            out.append(rec)
        return out

    def link_requirement(self, requirement_id: str, project_id: str, key: str, revision: int,
                         supersedes: str | None, stage: str, source: dict[str, Any]) -> None:
        with self.database.write() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO project_requirement_links(requirement_id, project_id, requirement_key, "
                "requirement_revision, supersedes_requirement_id, stage, source_json, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (requirement_id, project_id, key, revision, supersedes, stage, dumps(source), utc_now_iso()),
            )

    def requirement_links(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.read() as conn:
            rows = conn.execute("SELECT * FROM project_requirement_links WHERE project_id = ? ORDER BY rowid", (project_id,)).fetchall()
        out = []
        for r in rows:
            rec = dict(r)
            rec["source"] = loads(rec.pop("source_json"), {})
            out.append(rec)
        return out

    def requirement_link(self, project_id: str, requirement_id: str) -> dict[str, Any] | None:
        return next((r for r in self.requirement_links(project_id) if r["requirement_id"] == requirement_id), None)

    # ---- run bindings and run verifications ----------------------------------------------------------------
    def get_binding(self, requirement_id: str, run_id: str) -> dict[str, Any] | None:
        with self.database.read() as conn:
            row = conn.execute("SELECT * FROM project_run_bindings WHERE requirement_id = ? AND run_id = ?",
                               (requirement_id, run_id)).fetchone()
        return None if row is None else dict(row)

    def insert_binding(self, requirement_id: str, run_id: str, project_id: str, run_requirement_id: str, intent_id: str) -> None:
        with self.database.write() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO project_run_bindings(requirement_id, run_id, project_id, run_requirement_id, "
                "intent_id, created_at) VALUES (?,?,?,?,?,?)",
                (requirement_id, run_id, project_id, run_requirement_id, intent_id, utc_now_iso()),
            )

    def record_run_verification(self, rec: dict[str, Any]) -> None:
        with self.database.write() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO project_run_verifications(project_id, run_id, verification_id, requirement_id, "
                "requirement_revision, run_requirement_id, evaluation_status, stage, run_status, "
                "evidence_references_json, evaluation_window_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (rec["project_id"], rec["run_id"], rec["verification_id"], rec["requirement_id"],
                 rec["requirement_revision"], rec["run_requirement_id"], rec["evaluation_status"], rec["stage"],
                 rec.get("run_status"), dumps(rec.get("evidence_references") or []),
                 dumps(rec.get("evaluation_window") or {}), utc_now_iso()),
            )

    def run_verifications(self, project_id: str, run_id: str | None = None) -> list[dict[str, Any]]:
        sql, args = "SELECT * FROM project_run_verifications WHERE project_id = ?", [project_id]
        if run_id:
            sql += " AND run_id = ?"
            args.append(run_id)
        with self.database.read() as conn:
            rows = conn.execute(sql + " ORDER BY created_at, rowid", args).fetchall()
        out = []
        for r in rows:
            rec = dict(r)
            rec["evidence_references"] = loads(rec.pop("evidence_references_json"), [])
            rec["evaluation_window"] = loads(rec.pop("evaluation_window_json"), {})
            out.append(rec)
        return out
