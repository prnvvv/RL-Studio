"""SQLAlchemy base for ORM models."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase

CustomBase = DeclarativeBase

# Backwards-compatible Base for code that imports from backend.database.base
# This mirrors the pattern used when SQLAlchemy 1.x style Base is expected.
Base = CustomBase
