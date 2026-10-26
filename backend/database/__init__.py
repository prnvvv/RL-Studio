"""Persistence foundation for Self-Healing RL Studio.

Person 4 owns this package: configuration, connections, migrations, and
repositories shared by provenance, recovery, and evaluation.
"""

from __future__ import annotations

from .config import DatabaseConfig
from .connection import Database
from .exceptions import (
    ArtifactPathError,
    BlockedOperationError,
    ConflictError,
    DatabaseError,
    IntegrityFailure,
    NotFoundError,
    OperationLockedError,
    StudioError,
    ValidationError,
)

__all__ = [
    "DatabaseConfig",
    "Database",
    "StudioError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "OperationLockedError",
    "IntegrityFailure",
    "BlockedOperationError",
    "DatabaseError",
    "ArtifactPathError",
]
