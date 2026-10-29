"""Experiment ORM model."""
from __future__ import annotations

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from backend.database.base import Base


class Experiment(Base):
    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(String(36), unique=True, nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.project_id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    environment_version = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
