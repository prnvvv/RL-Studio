"""SQLite connection lifecycle and transaction boundaries."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from .config import DatabaseConfig
from .exceptions import DatabaseError
from .migrations import apply_migrations


class Database:
    """Creates short-lived SQLite connections with explicit transactions.

    A new connection is used per operation rather than one global engine.  This
    keeps the foundation dependency-free and safe to call from FastAPI's worker
    threads.  Write transactions use ``BEGIN IMMEDIATE`` so migration and
    state-transition checks cannot race silently.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config

    def _connect(self) -> sqlite3.Connection:
        try:
            self.config.database_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self.config.database_path),
                timeout=self.config.busy_timeout_ms / 1000,
                isolation_level=None,
                check_same_thread=False,
            )
        except (OSError, sqlite3.Error) as exc:
            raise DatabaseError("Unable to open the database") from exc
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {int(self.config.busy_timeout_ms)}")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        except sqlite3.Error as exc:
            raise DatabaseError("Database read failed") from exc
        finally:
            conn.close()

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            if isinstance(exc, sqlite3.IntegrityError):
                raise
            raise DatabaseError("Database write failed") from exc
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        self.config.artifact_root.mkdir(parents=True, exist_ok=True)
        with self.write() as conn:
            apply_migrations(conn)

    def healthcheck(self) -> bool:
        with self.read() as conn:
            conn.execute("SELECT 1").fetchone()
        return True

    def artifact_path(self, relative_path: str) -> Path:
        from .paths import resolve_artifact_path

        return resolve_artifact_path(self.config.artifact_root, relative_path)
