"""Canonical incident, recovery, and evaluation contracts (AGENTS.md §7.4, §7.5).

Re-exports from shared.schemas for inter-module consistency.
These models deliberately keep three things distinct so the UI and audit trail
can report them honestly: detection status, diagnosis status, and
recovery/evaluation status.
"""

from __future__ import annotations

from shared.schemas.contracts import (
    CompatibilityCheck,
    Evaluation,
    EvaluationStatus,
    Incident,
    IncidentStatus,
    MetricResult,
    Recovery,
    RecoveryAction,
    RecoveryStatus,
    RootCauseStatus,
    ViolationSeverity,
)

__all__ = [
    "CompatibilityCheck",
    "Evaluation",
    "EvaluationStatus",
    "Incident",
    "IncidentStatus",
    "MetricResult",
    "Recovery",
    "RecoveryAction",
    "RecoveryStatus",
    "RootCauseStatus",
    "ViolationSeverity",
]