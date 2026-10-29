"""Database session management."""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from backend.database.config import DatabaseConfig
from backend.database.connection import Database

_db: Database | None = None


def get_database(config: DatabaseConfig | None = None) -> Database:
    global _db
    if _db is None:
        _db = Database(config or DatabaseConfig.from_env())
        _db.initialize()
    return _db


@contextmanager
def session_scope(config: DatabaseConfig | None = None) -> Generator:
    db = get_database(config)
    conn = db.connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
