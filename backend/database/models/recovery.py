"""Recovery ORM model."""
from __future__ import annotations

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON

from backend.database.base import Base


class Recovery(Base):
    __tablename__ = "recoveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recovery_id = Column(String(36), unique=True, nullable=False, index=True)
    incident_id = Column(String(36), ForeignKey("incidents.incident_id"), nullable=False)
    source_checkpoint_id = Column(String(64), nullable=True)
    target_checkpoint_id = Column(String(64), nullable=True)
    status = Column(String(20), default="planned")
    executed_at = Column(DateTime(timezone=True), nullable=True)
    metadata = Column(JSON, default="{}")
