"""Database session management."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Optional

from backend.database.config import DatabaseConfig
from backend.database.connection import Database


_db: Optional[Database] = None


def get_database(config: Optional[DatabaseConfig] = None) -> Database:
    global _db
    if _db is None:
        _db = Database(config or DatabaseConfig.from_env())
        _db.initialize()
    return _db


@contextmanager
def session_scope(config: Optional[DatabaseConfig] = None) -> Generator:
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
