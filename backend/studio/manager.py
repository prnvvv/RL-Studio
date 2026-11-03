"""Registry of studio sessions with bounded retention and a single-trainer guard."""

from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from typing import Any

from backend.database.exceptions import ConflictError, NotFoundError

from .session import ACTIVE, Status, TrainingSession, data_dir, validate_config

logger = logging.getLogger(__name__)

MAX_SESSIONS = 20
_SESSION_ID = re.compile(r"^ses_[0-9a-f]{8}$")


class SessionManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, TrainingSession] = {}

    def create(self, raw: dict[str, Any], name: str | None = None) -> TrainingSession:
        config = validate_config(raw)
        clean_name = (name or "").strip()[:80] or None
        with self._lock:
            self._evict_if_full()
            session = TrainingSession(f"ses_{uuid.uuid4().hex[:8]}", config, clean_name)
            self._sessions[session.session_id] = session
            return session

    def get(self, session_id: str) -> TrainingSession:
        with self._lock:
            session = self._sessions.get(session_id) if _SESSION_ID.match(session_id) else None
        if session is None:
            raise NotFoundError("Session not found", details={"session_id": session_id[:40]})
        return session

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._sessions.values())
        return [s.summary() for s in sorted(sessions, key=lambda s: s.created_at, reverse=True)]

    def start(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        with self._lock:
            busy = [s for s in self._sessions.values() if s is not session and s.status in ACTIVE]
            if busy and session.status == Status.INITIALIZED:
                raise ConflictError(
                    "Another session is already training; stop it before starting a new one",
                    details={"active_session_id": busy[0].session_id},
                )
            return session.start()

    def _evict_if_full(self) -> None:
        if len(self._sessions) < MAX_SESSIONS:
            return
        evictable = sorted(
            (s for s in self._sessions.values() if s.status not in ACTIVE),
            key=lambda s: s.created_at,
        )
        if not evictable:
            raise ConflictError("Too many active sessions")
        del self._sessions[evictable[0].session_id]

    def history(self) -> list[dict[str, Any]]:
        """Persisted experiment records, newest first (summary only)."""
        directory = data_dir() / "sessions"
        if not directory.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(directory.glob("ses_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:50]:
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                logger.warning("Skipping unreadable experiment record %s", path.name)
                continue
            records.append({k: data.get(k) for k in ("session_id", "run_id", "name", "status", "agent", "environment", "created_at", "finished_at", "progress", "checkpoints", "error")})
        return records

    def history_record(self, run_id: str) -> dict[str, Any]:
        if not re.match(r"^ses_[0-9a-f]{8}_r[0-9]{1,4}$", run_id):
            raise NotFoundError("Experiment record not found")
        path = data_dir() / "sessions" / f"{run_id}.json"
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            raise NotFoundError("Experiment record not found") from None


manager = SessionManager()
