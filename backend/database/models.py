"""SQLModel-backed persistence for runs, events, incidents, recoveries, evaluations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    JSON,
    create_engine,
)
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from shared.schemas import new_uuid, utc_now

Base = declarative_base()


class RunRecord(Base):
    __tablename__ = "runs"

    run_id = Column(String, primary_key=True, index=True)
    status = Column(String, default="created")
    config_fingerprint = Column(String, nullable=False)
    seed = Column(Integer, nullable=False)
    total_timesteps = Column(Integer, default=10_000)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class EventRecord(Base):
    __tablename__ = "events"

    event_id = Column(String, primary_key=True, index=True)
    event_type = Column(String, nullable=False)
    run_id = Column(String, index=True)
    environment_id = Column(String, nullable=True)
    environment_version = Column(String, nullable=True)
    episode_id = Column(String, nullable=True)
    timestep = Column(Integer, default=0)
    sequence = Column(Integer, default=0)
    payload = Column(JSON, nullable=False)
    source_component = Column(String, nullable=False)
    source_version = Column(String, nullable=True)
    timestamp = Column(DateTime, default=utc_now)
    correlation_id = Column(String, nullable=True)
    cause_id = Column(String, nullable=True)


class IncidentRecord(Base):
    __tablename__ = "incidents"

    incident_id = Column(String, primary_key=True, index=True)
    run_id = Column(String, index=True)
    requirement_id = Column(String, nullable=True)
    environment_version = Column(String, nullable=True)
    environment_id = Column(String, nullable=True)
    violation_type = Column(String, nullable=False)
    severity = Column(String, default="medium")
    status = Column(String, default="open")
    detection_status = Column(String, default="confirmed")
    diagnosis_status = Column(String, default="unresolved")
    evidence_event_ids = Column(JSON, default=lambda: [])
    evidence_refs = Column(JSON, default=lambda: [])
    detector_id = Column(String, nullable=True)
    detector_version = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    resolved_at = Column(DateTime, nullable=True)


class RecoveryRecord(Base):
    __tablename__ = "recoveries"

    recovery_id = Column(String, primary_key=True, index=True)
    incident_id = Column(String, index=True)
    proposed_actions = Column(JSON, default=lambda: [])
    executed_actions = Column(JSON, default=lambda: [])
    source_checkpoint_id = Column(String, nullable=True)
    target_checkpoint_id = Column(String, nullable=True)
    environment_fingerprint = Column(String, nullable=True)
    agent_config_fingerprint = Column(String, nullable=True)
    compatibility_checks = Column(JSON, default=lambda: [])
    approval_state = Column(String, default="pending")
    status = Column(String, default="planned")
    failure_reason = Column(String, nullable=True)
    evaluation_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class EvaluationRecord(Base):
    __tablename__ = "evaluations"

    evaluation_id = Column(String, primary_key=True, index=True)
    recovery_id = Column(String, nullable=True)
    run_id = Column(String, nullable=True)
    environment_version = Column(String, nullable=False)
    policy_fingerprint = Column(String, nullable=True)
    n_episodes = Column(Integer, default=1)
    n_seeds = Column(Integer, default=1)
    seeds = Column(JSON, default=lambda: [])
    metrics = Column(JSON, default=lambda: "[]")
    baselines = Column(JSON, default=lambda: "[]")
    acceptance_criteria = Column(JSON, default=lambda: "{}")
    status = Column(String, default="pending")
    outcome = Column(String, nullable=True)
    limitations = Column(JSON, default=lambda: "[]")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


def get_engine(db_path: str = "sqlite:///rl_studio.db") -> Any:
    """Return a SQLAlchemy engine instance."""
    return create_engine(db_path, echo=False, future=True)


def get_session_factory(engine: Any) -> sessionmaker[Session]:
    """Return a configured Session factory bound to the engine."""
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def init_db(db_path: str = "sqlite:///rl_studio.db") -> None:
    """Create all tables (idempotent)."""
    Base.metadata.create_all(bind=get_engine(db_path))