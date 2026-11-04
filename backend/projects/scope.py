"""Server-side project isolation.

A request may carry a *project scope*: the ``X-Project-ID`` header, or ``?project_id=`` for WebSocket/SSE clients
that cannot set headers. Every resource that belongs to a run (a run, its incident, an artifact, a verification,
an intent, a requirement, a Studio session) has exactly one owner:

* a project id (``runs.project_id``, or the ``project:<id>`` pseudo run of a project-level requirement), or
* ``None`` - an unassigned / legacy record that predates projects.

The rule, applied by one dependency to every router that exposes such resources:

    owner == scope           -> allowed
    owner is a project, scope differs or is absent -> 404
    owner is None (legacy), scope is a project      -> 404  (legacy data is only visible unscoped)
    owner is None, no scope                          -> allowed (unchanged legacy behaviour)

The answer is always 404, never 403, so a guessed or modified id does not even reveal that the record exists.
The frontend never decides this: it only sends its active project, and the backend enforces the rule.
Deleting a project hides its data (its scope is rejected, and unscoped requests are refused too); nothing is removed.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, WebSocketException, status
from starlette.requests import HTTPConnection

from backend.database.connection import Database
from backend.projects.repository import ProjectRepository

HEADER = "x-project-id"
QUERY = "project_id"
_PROJECT_ID = re.compile(r"^prj_[0-9a-f]{16}$")
PROJECT_SCOPE_PREFIX = "project:"

#: path/query parameter name -> (table, id column, run column) used to find the owning run
_RESOURCES: dict[str, tuple[str, str, str]] = {
    "incident_id": ("incidents", "incident_id", "run_id"),
    "artifact_id": ("artifacts", "artifact_id", "run_id"),
    "intent_id": ("verification_intents", "intent_id", "run_id"),
    "requirement_id": ("verification_requirements", "requirement_id", "run_id"),
    "verification_id": ("verifications", "verification_id", "run_id"),
    "evaluation_id": ("evaluations", "evaluation_id", "incident_id"),  # resolved through its incident
}
_RUN_KEYS = ("run_id", "baseline_run_id", "recovered_run_id")


class Denied(Exception):
    """The caller's scope does not own the record (surfaced as 404)."""


def requested_scope(conn: HTTPConnection) -> str | None:
    raw = conn.headers.get(HEADER) or conn.query_params.get(QUERY)
    if raw is None or raw == "":
        return None
    return raw.strip()


def owner_of_run(database: Database, run_id: str) -> str | None:
    if run_id.startswith(PROJECT_SCOPE_PREFIX):
        return run_id[len(PROJECT_SCOPE_PREFIX):]
    with database.read() as db:
        row = db.execute("SELECT project_id FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return None if row is None else row["project_id"]


def _owner_via(database: Database, key: str, value: str) -> str | None:
    table, id_col, run_col = _RESOURCES[key]
    with database.read() as db:
        row = db.execute(f"SELECT {run_col} FROM {table} WHERE {id_col} = ?", (value,)).fetchone()
    if row is None:
        return None
    if key == "evaluation_id":
        return _owner_via(database, "incident_id", row[run_col])
    if key == "incident_id" or run_col == "run_id":
        return owner_of_run(database, row[run_col]) if row[run_col] else None
    return None


def _session_owner(session_id: str) -> str | None:
    from backend.studio.manager import manager

    session = manager._sessions.get(session_id)
    return getattr(session, "project_id", None)


def _battle_owner(battle_id: str) -> str | None:
    from backend.studio.manager import manager

    sides = manager._battles.get(battle_id) or {}
    for session_id in sides.values():
        return _session_owner(session_id)
    return None


def validate_scope(database: Database, scope: str | None) -> str | None:
    """A scope must be a well-formed id of an existing, non-deleted project."""
    if scope is None:
        return None
    if not _PROJECT_ID.match(scope) or ProjectRepository(database).get_project(scope) is None:
        raise Denied("unknown project")
    return scope


def check_owner(owner: str | None, scope: str | None) -> None:
    if owner != scope:
        raise Denied("not in this project")


def check_run(database: Database, run_id: str, scope: str | None) -> None:
    check_owner(owner_of_run(database, run_id), scope)


def authorize(conn: HTTPConnection, database: Database, params: dict[str, Any]) -> None:
    """Check every identifier in ``params`` (path/query values) against the request scope."""
    scope = validate_scope(database, requested_scope(conn))
    for key in _RUN_KEYS:
        value = params.get(key)
        if isinstance(value, str) and value:
            check_run(database, value, scope)
    for key in _RESOURCES:
        value = params.get(key)
        if isinstance(value, str) and value:
            check_owner(_owner_via(database, key, value), scope)
    session_id = params.get("session_id")
    if isinstance(session_id, str) and session_id:
        check_owner(_session_owner(session_id), scope)
    battle_id = params.get("battle_id")
    if isinstance(battle_id, str) and battle_id:
        check_owner(_battle_owner(battle_id), scope)


async def enforce_project_scope(conn: HTTPConnection) -> None:
    """Router-level dependency (HTTP and WebSocket)."""
    database = getattr(conn.app.state, "database", None)
    if database is None:
        return  # application not ready: the endpoint reports the 503 itself
    params: dict[str, Any] = {**conn.query_params, **conn.path_params}
    try:
        authorize(conn, database, params)
    except Denied as exc:
        if conn.scope["type"] == "websocket":
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="not found") from exc
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "The requested record was not found.", "details": {}}},
        ) from exc


def scope_of(conn: HTTPConnection) -> str | None:
    """The validated scope, for endpoints that filter lists or create records."""
    database = getattr(conn.app.state, "database", None)
    try:
        return validate_scope(database, requested_scope(conn)) if database is not None else None
    except Denied as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "The requested record was not found.", "details": {}}},
        ) from exc


def run_owners(database: Database) -> dict[str, str | None]:
    """run_id -> owning project for every registered run (used to filter lists)."""
    with database.read() as db:
        return {r["run_id"]: r["project_id"] for r in db.execute("SELECT run_id, project_id FROM runs")}


__all__ = [
    "Denied", "authorize", "check_owner", "check_run", "enforce_project_scope", "owner_of_run", "requested_scope",
    "run_owners", "scope_of", "validate_scope",
]
