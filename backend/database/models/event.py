"""Execution event ORM model."""
from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func

from backend.database.base import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(36), unique=True, nullable=False, index=True)
    run_id = Column(String(36), ForeignKey("runs.run_id"), nullable=False)
    event_type = Column(String(50), nullable=False)
    episode_id = Column(String(36), nullable=True)
    timestep = Column(Integer, default=0)
    actual_reward = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
