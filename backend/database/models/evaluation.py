"""Evaluation ORM model."""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from backend.database.base import Base


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    evaluation_id = Column(String(36), unique=True, nullable=False, index=True)
    run_id = Column(String(36), ForeignKey("runs.run_id"), nullable=False)
    evaluation_environment_version = Column(String(50), nullable=False)
    episode_count = Column(Integer, default=100)
    success = Column(Boolean, nullable=True)
    metrics = Column(JSON, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
