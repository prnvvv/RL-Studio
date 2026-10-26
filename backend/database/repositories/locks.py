from __future__ import annotations

import sqlite3
from datetime import timedelta

from ..exceptions import OperationLockedError
from ..utils import new_id, to_iso, utc_now


def acquire_lock(
    conn: sqlite3.Connection,
    *,
    lock_key: str,
    ttl_seconds: int = 300,
    owner_id: str | None = None,
) -> str:
    owner = owner_id or new_id("owner")
    now = utc_now()
    expires = now + timedelta(seconds=max(1, ttl_seconds))
    conn.execute(
        "DELETE FROM operation_locks WHERE expires_at <= ?",
        (to_iso(now),),
    )
    try:
        conn.execute(
            """
            INSERT INTO operation_locks(lock_key, owner_id, acquired_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (lock_key, owner, to_iso(now), to_iso(expires)),
        )
    except sqlite3.IntegrityError as exc:
        raise OperationLockedError(
            "Another operation is already in progress for this scope",
            details={"lock_key": lock_key},
        ) from exc
    return owner


def release_lock(conn: sqlite3.Connection, *, lock_key: str, owner_id: str) -> None:
    conn.execute(
        "DELETE FROM operation_locks WHERE lock_key = ? AND owner_id = ?",
        (lock_key, owner_id),
    )
