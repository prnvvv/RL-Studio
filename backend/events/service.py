"""Event store publisher."""
from __future__ import annotations

from uuid import uuid4
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Table, select, Column, String, Integer, DateTime, MetaData, Float
from backend.database.base import Base, engine

# Event table definition (matching shared.events canon)
metadata = MetaData()
execution_events = Table(
    "execution_events",
    metadata,
    Column("event_id", String(36), primary_key=True),
    Column("run_id", String(36), index=True),
    Column("event_type", String(50), nullable=False),
    Column("episode_id", String(36), nullable=True),
    Column("timestep", Integer, nullable=True),
    Column("actual_reward", Float, nullable=True),
    Column("timestamp", DateTime(timezone=True), server_default="CURRENT_TIMESTAMP"),
)
metadata.create_all(bind=engine)


class Event:
    """Pydantic-model-like representation of a persisted event."""
    def __init__(
        self,
        event_id: str,
        run_id: str,
        event_type: str,
        episode_id: Optional[str],
        timestep: Optional[int],
        actual_reward: Optional[float],
        timestamp: datetime,
    ):
        self.event_id = event_id
        self.run_id = run_id
        self.event_type = event_type
        self.episode_id = episode_id
        self.timestep = timestep
        self.actual_reward = actual_reward
        self.timestamp = timestamp

    def model_dump(self, mode: str = "python") -> Dict[str, Any]:
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
        event_id = str(uuid4())
        with engine.begin() as conn:
            conn.execute(
                """
                INSERT INTO execution_events
                (event_id, run_id, event_type, episode_id, timestep, actual_reward, timestamp)
                VALUES (:event_id, :run_id, :event_type, :episode_id, :timestep, :actual_reward, :timestamp)
                """,
                {
                    "event_id": event_id,
                    "run_id": run_id,
                    "event_type": event_type,
                    "episode_id": episode_id,
                    "timestep": timestep,
                    "actual_reward": actual_reward,
                    "timestamp": datetime.now(timezone.utc),
                },
            )
        return event_id

    @staticmethod
    def get_recent_events(run_id: str, limit: int = 20) -> List[Event]:
        """Get the most recent events for a given run, ordered by timestamp desc."""
        with engine.begin() as conn:
            stmt = (
                select(execution_events)
                .where(execution_events.c.run_id == run_id)
                .order_by(execution_events.c.timestamp.desc())
                .limit(limit)
            )
            rows = conn.execute(stmt).fetchall()
            events: List[Event] = []
            for row in rows:
                event = Event(
                    event_id=row.event_id,
                    run_id=row.run_id,
                    event_type=row.event_type,
                    episode_id=row.episode_id,
                    timestep=row.timestep,
                    actual_reward=row.actual_reward,
                    timestamp=row.timestamp,
                )
                events.append(event)
            return events
