"""Durable execution event store (AGENTS.md §7.2).

Event types match the canonical ``shared.schemas.events`` contract.  The
low-level table lives in :mod:`backend.events.service`; this module only
exposes the stable event-type identifiers.
"""

from __future__ import annotations

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

__all__ = ["event_types"]
