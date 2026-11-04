"""Database and artifact storage configuration.

The defaults keep local development data inside ``<repo>/var`` which is already
ignored by the repository.  Deployments should override the paths with
environment variables rather than editing code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return Path(raw).expanduser().resolve()


@dataclass(frozen=True)
class DatabaseConfig:
    """Runtime database configuration.

    If ``DATABASE_URL`` is set, a Postgres connection is used via psycopg2.
    Otherwise, SQLite is used as the default.
    """

    database_path: Path
    artifact_root: Path
    busy_timeout_ms: int = 5000
    max_artifact_bytes: int = 2 * 1024 * 1024 * 1024
    use_postgres: bool = False
    postgres_dsn: str = ""

    @classmethod
    def from_env(cls) -> DatabaseConfig:
        use_postgres = os.environ.get("DATABASE_URL", "").strip() != ""
        data_root = _env_path("RL_STUDIO_DATA_ROOT", _repo_root() / "var")
        database_path = _env_path(
            "RL_STUDIO_DB_PATH", data_root / "rl_studio.sqlite3"
        )
        artifact_root = _env_path(
            "RL_STUDIO_ARTIFACT_ROOT", data_root / "artifacts"
        )
        busy_timeout_ms = int(os.environ.get("RL_STUDIO_DB_BUSY_TIMEOUT_MS", "5000"))
        max_artifact_bytes = int(
            os.environ.get("RL_STUDIO_MAX_ARTIFACT_BYTES", str(2 * 1024 * 1024 * 1024))
        )
        postgres_dsn = os.environ.get("DATABASE_URL", "")
        return cls(
            database_path=database_path,
            artifact_root=artifact_root,
            busy_timeout_ms=busy_timeout_ms,
            max_artifact_bytes=max_artifact_bytes,
            use_postgres=use_postgres,
            postgres_dsn=postgres_dsn,
        )

    @classmethod
    def for_tests(cls, root: Path) -> DatabaseConfig:
        root = Path(root).resolve()
        return cls(
            database_path=root / "test.sqlite3",
            artifact_root=root / "artifacts",
            busy_timeout_ms=1000,
            max_artifact_bytes=64 * 1024 * 1024,
        )
