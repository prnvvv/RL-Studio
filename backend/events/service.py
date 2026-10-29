"""Event store publisher backed by the shared SQLite ``Database``."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.database.config import DatabaseConfig
from backend.database.connection import Database

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS execution_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT,
    event_type TEXT NOT NULL,
    episode_id TEXT,
    timestep INTEGER,
    actual_reward REAL,
    timestamp TEXT
)
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_execution_events_run_id
ON execution_events (run_id)
"""

_db: Database | None = None
_schema_ready = False
_schema_lock = threading.Lock()


def _database() -> Database:
    """Return the lazily created database handle for the event store."""
    global _db
    if _db is None:
        _db = Database(DatabaseConfig.from_env())
    return _db


def _ensure_schema(database: Database) -> None:
    """Create the event table on first use (idempotent)."""
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        with database.write() as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.execute(_CREATE_INDEX_SQL)
        _schema_ready = True


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse a stored ISO-8601 timestamp into an aware ``datetime``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class Event:
    """Pydantic-model-like representation of a persisted event."""

    def __init__(
        self,
        event_id: str,
        run_id: str,
        event_type: str,
        episode_id: str | None,
        timestep: int | None,
        actual_reward: float | None,
        timestamp: datetime | None,
    ):
        self.event_id = event_id
        self.run_id = run_id
        self.event_type = event_type
        self.episode_id = episode_id
        self.timestep = timestep
        self.actual_reward = actual_reward
        self.timestamp = timestamp

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "timestep": self.timestep,
            "actual_reward": self.actual_reward,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class EventPublisher:
    """Persist schema-validated execution events to the database."""

    @staticmethod
    def publish(
        event_type: str,
        run_id: str,
        episode_id: str | None = None,
        timestep: int | None = None,
        actual_reward: float | None = None,
    ) -> str:
        database = _database()
        _ensure_schema(database)
        event_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        with database.write() as conn:
            conn.execute(
                """
                INSERT INTO execution_events
                (event_id, run_id, event_type, episode_id, timestep, actual_reward, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    run_id,
                    event_type,
                    episode_id,
                    timestep,
                    actual_reward,
                    timestamp,
                ),
            )
        return event_id

    @staticmethod
    def get_recent_events(run_id: str, limit: int = 20) -> list[Event]:
        """Get the most recent events for a given run, ordered by timestamp desc."""
        database = _database()
        _ensure_schema(database)
        with database.read() as conn:
            rows = conn.execute(
                """
                SELECT event_id, run_id, event_type, episode_id, timestep,
                       actual_reward, timestamp
                FROM execution_events
                WHERE run_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
        return [
            Event(
                event_id=row["event_id"],
                run_id=row["run_id"],
                event_type=row["event_type"],
                episode_id=row["episode_id"],
                timestep=row["timestep"],
                actual_reward=row["actual_reward"],
                timestamp=_parse_timestamp(row["timestamp"]),
            )
            for row in rows
        ]
