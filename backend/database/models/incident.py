"""Incident ORM model."""
from __future__ import annotations

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from backend.database.base import Base


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(String(36), unique=True, nullable=False, index=True)
    run_id = Column(String(36), ForeignKey("runs.run_id"), nullable=False)
    requirement_id = Column(String(36), nullable=False)
    severity = Column(String(20), default="medium")
    status = Column(String(20), default="detected")
    detection_method = Column(String(30), default="verification")
    environment_version = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
