"""Shared-file safety review for the project-management migrations (3 and 4).

These guard the properties a Person 4 reviewer needs: the new migrations only *add* tables and indexes, never touch
an existing column or row, can be applied on top of a database that already holds data, and are idempotent.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from backend.database import migrations as m

LEGACY = tuple(mig for mig in m.MIGRATIONS if mig.version <= 2)
NEW = tuple(mig for mig in m.MIGRATIONS if mig.version >= 3)
FORBIDDEN = re.compile(r"\b(ALTER|DROP|DELETE|UPDATE|INSERT|REPLACE|TRUNCATE|PRAGMA)\b", re.IGNORECASE)
ALLOWED = re.compile(r"^\s*CREATE\s+(TABLE|INDEX)\s+IF\s+NOT\s+EXISTS\b", re.IGNORECASE)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _schema(conn: sqlite3.Connection) -> dict[str, list[tuple[Any, ...]]]:
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    return {t: [tuple(c) for c in conn.execute(f"PRAGMA table_info({t})")] for t in tables}


def test_new_migrations_only_create_tables_and_indexes() -> None:
    assert [mig.version for mig in NEW] == [3, 4]
    for mig in NEW:
        for statement in mig.statements:
            assert ALLOWED.match(statement), f"migration {mig.version}: not an idempotent CREATE: {statement[:60]!r}"
            assert not FORBIDDEN.search(statement), f"migration {mig.version} contains a destructive keyword"


def test_new_migrations_do_not_redefine_any_existing_table() -> None:
    existing = set()
    for mig in LEGACY:
        for statement in mig.statements:
            found = re.match(r"\s*CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)", statement, re.IGNORECASE)
            if found:
                existing.add(found.group(1))
    created = set()
    for mig in NEW:
        for statement in mig.statements:
            found = re.match(r"\s*CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)", statement, re.IGNORECASE)
            if found:
                created.add(found.group(1))
    assert created and not (created & existing)


def test_upgrade_preserves_existing_schema_and_rows() -> None:
    conn = _connect()
    assert m.apply_migrations(conn, LEGACY) == [1, 2]
    conn.execute(
        "INSERT INTO runs(run_id, project_id, status, metadata_json, created_at, updated_at) VALUES ('r1', NULL, 'completed', '{}', 't', 't')"
    )
    conn.execute(
        "INSERT INTO incidents(incident_id, run_id, status, evidence_ids_json, details_json, created_at, updated_at) "
        "VALUES ('i1', 'r1', 'detected', '[]', '{}', 't', 't')"
    )
    conn.execute(
        "INSERT INTO audit_events(audit_id, entity_type, entity_id, action, status, details_json, created_at) "
        "VALUES ('a1', 'run', 'r1', 'registered', 'ok', '{}', 't')"
    )
    conn.execute(
        "INSERT INTO verifications(verification_id, run_id, overall_status, idempotency_key, output_json, created_at) "
        "VALUES ('v1', 'r1', 'fail', 'k', '{}', 't')"
    )
    before = _schema(conn)
    rows_before = {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in ("runs", "incidents", "audit_events", "verifications")}

    assert m.apply_migrations(conn, m.MIGRATIONS) == [3, 4]

    after = _schema(conn)
    for table, columns in before.items():
        assert after[table] == columns, f"{table} changed"  # no column added, removed or retyped
    assert {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in rows_before} == rows_before
    assert {"projects", "project_documents", "project_intent_links", "project_requirement_links",
            "project_run_bindings", "project_run_verifications", "project_requirement_policies"} <= set(after)


def test_migrations_are_idempotent_and_recorded_in_order() -> None:
    conn = _connect()
    assert m.apply_migrations(conn) == [1, 2, 3, 4]
    assert m.apply_migrations(conn) == []
    assert [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")] == [1, 2, 3, 4]


def test_audit_log_stays_append_only() -> None:
    conn = _connect()
    m.apply_migrations(conn)
    conn.execute("INSERT INTO audit_events(audit_id, entity_type, entity_id, action, status, details_json, created_at) VALUES ('a','x','y','z','ok','{}','t')")
    for sql in ("UPDATE audit_events SET status='x'", "DELETE FROM audit_events"):
        try:
            conn.execute(sql)
        except sqlite3.DatabaseError as exc:
            assert "append-only" in str(exc)
        else:  # pragma: no cover
            raise AssertionError(f"{sql} was allowed")


def test_the_run_to_project_association_reuses_the_existing_column() -> None:
    """Person 4's ``runs.project_id`` (migration 1) is the association; the project migrations add only an index."""
    conn = _connect()
    m.apply_migrations(conn)
    columns = {c["name"] for c in conn.execute("PRAGMA table_info(runs)")}
    assert "project_id" in columns
    assert any(r["name"] == "idx_runs_project" for r in conn.execute("PRAGMA index_list(runs)"))
