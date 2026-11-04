"""Event store publisher backed by the shared SQLite ``Database``."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

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

#: Columns added after the original schema; applied additively so existing databases keep working.
_ADDED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("environment_id", "TEXT"),
    ("environment_version", "TEXT"),
    ("agent_id", "TEXT"),
    ("terminated", "INTEGER"),
    ("truncated", "INTEGER"),
    ("metrics_json", "TEXT"),
    ("metadata_json", "TEXT"),
    ("idempotency_key", "TEXT"),
)
_CREATE_IDEMPOTENCY_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_execution_events_idempotency
ON execution_events (idempotency_key) WHERE idempotency_key IS NOT NULL
"""

_db: Database | None = None
_explicit = False
_schema_ready = False
_schema_lock = threading.Lock()


def _database() -> Database:
    """Return the event-store database handle.

    Unless explicitly configured, the handle follows the environment-derived config so a changed
    ``RL_STUDIO_DATA_ROOT`` (tests, deployments) is honoured instead of a stale cached path.
    """
    global _db, _schema_ready
    if _explicit and _db is not None:
        return _db
    config = DatabaseConfig.from_env()
    if _db is None or _db.config != config:
        with _schema_lock:
            _db = Database(config)
            _schema_ready = False
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
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(execution_events)")}
            for name, decl in _ADDED_COLUMNS:
                if name not in existing:
                    conn.execute(f"ALTER TABLE execution_events ADD COLUMN {name} {decl}")
            conn.execute(_CREATE_IDEMPOTENCY_INDEX_SQL)
        _schema_ready = True


def configure(database: Database | None) -> None:
    """Point the event store at ``database`` (tests / app wiring); ``None`` resets to env defaults."""
    global _db, _schema_ready, _explicit
    with _schema_lock:
        _db = database
        _explicit = database is not None
        _schema_ready = False


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
    """Canonical execution event as persisted."""

    def __init__(
        self,
        event_id: str,
        run_id: str,
        event_type: str,
        episode_id: str | None,
        timestep: int | None,
        actual_reward: float | None,
        timestamp: datetime | None,
        *,
        environment_id: str | None = None,
        environment_version: str | None = None,
        agent_id: str | None = None,
        terminated: bool | None = None,
        truncated: bool | None = None,
        metrics: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.event_id = event_id
        self.run_id = run_id
        self.event_type = event_type
        self.episode_id = episode_id
        self.timestep = timestep
        self.actual_reward = actual_reward
        self.timestamp = timestamp
        self.environment_id = environment_id
        self.environment_version = environment_version
        self.agent_id = agent_id
        self.terminated = terminated
        self.truncated = truncated
        self.metrics = metrics or {}
        self.metadata = metadata or {}

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "run_id": self.run_id,
            "episode_id": self.episode_id,
            "timestep": self.timestep,
            "actual_reward": self.actual_reward,
            "reward": self.actual_reward,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "terminated": self.terminated,
            "truncated": self.truncated,
            "environment_id": self.environment_id,
            "environment_version": self.environment_version,
            "agent_id": self.agent_id,
            "metrics": self.metrics,
            "metadata": self.metadata,
        }


_COLUMNS = (
    "event_id, run_id, event_type, episode_id, timestep, actual_reward, timestamp, "
    "environment_id, environment_version, agent_id, terminated, truncated, "
    "metrics_json, metadata_json"
)


def _flag(value: Any) -> bool | None:
    return None if value is None else bool(value)


def _loads(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value) if value else {}
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _row_to_event(row: Any) -> Event:
    return Event(
        event_id=row["event_id"],
        run_id=row["run_id"],
        event_type=row["event_type"],
        episode_id=row["episode_id"],
        timestep=row["timestep"],
        actual_reward=row["actual_reward"],
        timestamp=_parse_timestamp(row["timestamp"]),
        environment_id=row["environment_id"],
        environment_version=row["environment_version"],
        agent_id=row["agent_id"],
        terminated=_flag(row["terminated"]),
        truncated=_flag(row["truncated"]),
        metrics=_loads(row["metrics_json"]),
        metadata=_loads(row["metadata_json"]),
    )


def stable_event_id(idempotency_key: str) -> str:
    """Deterministic event id for an idempotency key (same key -> same id)."""
    return str(uuid5(NAMESPACE_URL, f"rl-studio:event:{idempotency_key}"))


class EventPublisher:
    """Persist canonical execution events to the database."""

    @staticmethod
    def publish(
        event_type: str,
        run_id: str,
        episode_id: str | None = None,
        timestep: int | None = None,
        actual_reward: float | None = None,
        *,
        idempotency_key: str | None = None,
        environment_id: str | None = None,
        environment_version: str | None = None,
        agent_id: str | None = None,
        terminated: bool | None = None,
        truncated: bool | None = None,
        metrics: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> str:
        """Persist one event and return its id.

        With an ``idempotency_key`` the id is deterministic and re-publishing the
        same key is a no-op that returns the original event id.
        """
        database = _database()
        _ensure_schema(database)
        event_id = stable_event_id(idempotency_key) if idempotency_key else str(uuid4())
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        with database.write() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO execution_events
                (event_id, run_id, event_type, episode_id, timestep, actual_reward, timestamp,
                 environment_id, environment_version, agent_id, terminated, truncated,
                 metrics_json, metadata_json, idempotency_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id, run_id, event_type, episode_id, timestep, actual_reward, ts,
                    environment_id, environment_version, agent_id,
                    None if terminated is None else int(terminated),
                    None if truncated is None else int(truncated),
                    json.dumps(metrics, sort_keys=True) if metrics else None,
                    json.dumps(metadata, sort_keys=True) if metadata else None,
                    idempotency_key,
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
                f"SELECT {_COLUMNS} FROM execution_events WHERE run_id = ? "
                "ORDER BY timestamp DESC, rowid DESC LIMIT ?",
                (run_id, limit),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    @staticmethod
    def list_run_events(run_id: str) -> list[Event]:
        """All events of a run in persisted (chronological, insertion) order."""
        database = _database()
        _ensure_schema(database)
        with database.read() as conn:
            rows = conn.execute(
                f"SELECT {_COLUMNS} FROM execution_events WHERE run_id = ? "
                "ORDER BY timestamp ASC, rowid ASC",
                (run_id,),
            ).fetchall()
        return [_row_to_event(row) for row in rows]
