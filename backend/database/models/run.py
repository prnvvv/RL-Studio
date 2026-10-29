"""Run ORM model."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from backend.database.base import Base


class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), unique=True, nullable=False, index=True)
    experiment_id = Column(String(36), ForeignKey("experiments.experiment_id"), nullable=False)
    environment_version = Column(String(50), nullable=False)
    seed = Column(Integer, nullable=False)
    status = Column(String(20), default="created")
    total_timesteps = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
