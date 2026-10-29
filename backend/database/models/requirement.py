"""Requirement ORM model."""
from __future__ import annotations

from sqlalchemy import Column, String, Float, DateTime, ForeignKey
from sqlalchemy.sql import func

from backend.database.base import Base


class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(String(36), unique=True, nullable=False, index=True)
    run_id = Column(String(36), ForeignKey("runs.run_id"), nullable=True)
    requirement_type = Column(String(30), nullable=False)
    expected_value = Column(Float, nullable=True)
    actual_value = Column(Float, nullable=True)
    status = Column(String(20), default="pending")
    tolerance = Column(Float, nullable=True)
    confirmation = Column(String(30), default="developer_confirmed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
