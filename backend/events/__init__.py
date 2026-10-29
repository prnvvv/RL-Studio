"""Durable execution event store (AGENTS.md §7.2)."""

from __future__ import annotations

from sqlalchemy import (
    Table, Column, String, Integer, DateTime, MetaData, Insert, Float
)
from backend.database.base import Base

# Event types matching shared.events canon
event_types = (
    "execution_started",
    "execution_stopped",
    "episode_started",
    "episode_ended",
    "step",
    "collision",
    "checkpoint_written",
    "metric_observed",
    "fault_injected",
    "requirement_violation",
)

metadata = MetaData()

execution_events = Table(
    "execution_events",
    metadata,
    Column("event_id", String(36), primary_key=True),
    Column("run_id", String(36), index=True),
    Column("event_type", String(50), nullable=False),
    Column("episode_id", String(36), nullable=True),
    Column("timestep", Integer, nullable=True),
    Column("actual_reward", Float, nullable=True),
    Column("timestamp", DateTime(timezone=True), server_default="CURRENT_TIMESTAMP"),
)
metadata.create_all(bind=None)  # table created when connected
