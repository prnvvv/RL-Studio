"""Checkpoint ORM model."""
from __future__ import annotations

from sqlalchemy import Column, String, DateTime, ForeignKey, Float, JSON
from sqlalchemy.sql import func

from backend.database.base import Base


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    checkpoint_id = Column(String(64), unique=True, nullable=False, index=True)
    run_id = Column(String(36), ForeignKey("runs.run_id"), nullable=False)
    environment_version = Column(String(50), nullable=False)
    hash = Column(String(64), nullable=False)
    algorithm = Column(String(30), default="PPO")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    metadata = Column(JSON, default="{}")
