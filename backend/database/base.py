"""SQLAlchemy base for ORM models."""
from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class CustomBase(DeclarativeBase):
    """Custom declarative base with naming conventions."""
    pass
