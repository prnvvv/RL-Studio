"""Per-session, thread-safe event hub with monotonic ordering.

Two channels are kept apart on purpose:

* ``events`` - lifecycle, logs, metrics, checkpoints. Ordered, bounded, and
  replayable by sequence number so a reconnecting client can resync.
* ``frame``  - high-frequency simulation state. Only the latest frame is kept;
  a slow client skips frames instead of building a backlog.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"


class SessionHub:
    def __init__(self, session_id: str, max_events: int = 5000) -> None:
        self.session_id = session_id
        self._lock = threading.Lock()
        self._seq = 0
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._frame: dict[str, Any] | None = None
        self._frame_seq = 0

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def publish(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            event = {
                "schema_version": SCHEMA_VERSION,
                "seq": self._seq,
                "type": event_type,
                "session_id": self.session_id,
                "timestamp": self._now(),
                "payload": payload,
            }
            self._events.append(event)
            return event

    def set_frame(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._frame_seq += 1
            self._frame = {
                "schema_version": SCHEMA_VERSION,
                "frame_seq": self._frame_seq,
                "type": "frame",
                "session_id": self.session_id,
                "timestamp": self._now(),
                "payload": payload,
            }

    def latest_frame(self) -> dict[str, Any] | None:
        with self._lock:
            return self._frame

    def recent(self, event_type: str, limit: int = 500) -> list[dict[str, Any]]:
        """Most recent events of one type, oldest first (used to seed snapshots)."""
        with self._lock:
            matching = [e for e in self._events if e["type"] == event_type]
        return matching[-limit:]

    def last_seq(self) -> int:
        with self._lock:
            return self._seq

    def since(self, seq: int, limit: int = 1000) -> tuple[list[dict[str, Any]], bool]:
        """Events with ``seq`` greater than the argument, plus a gap flag.

        The flag is true when the requested position has already been evicted,
        meaning the caller missed events and should rely on a fresh snapshot.
        """
        with self._lock:
            if not self._events:
                return [], False
            oldest = self._events[0]["seq"]
            gap = seq + 1 < oldest
            out = [e for e in self._events if e["seq"] > seq]
            return out[:limit], gap
