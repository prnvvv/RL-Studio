"""Typed state for the RL Studio verification LangGraph workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.verification.models import (
    CheckStatus,
    VerificationCheckResult,
    VerificationContext,
    VerificationInput,
)


@dataclass
class VerificationState:
    """State carried across LangGraph workflow nodes."""

    # Input data
    raw_input: dict[str, Any] | None = None
    input: VerificationInput | None = None
    context: VerificationContext | None = None

    # Requirement and check state
    requirements: dict[str, Any] = field(default_factory=dict)
    check_results: dict[str, VerificationCheckResult] = field(default_factory=dict)
    registered_checks: list[str] = field(default_factory=list)

    # Aggregation and decision
    overall_status: CheckStatus | None = None
    decision_details: str = ""

    # Workflow control
    step: str = "start"  # start, normalizing, planning, checking, aggregating, complete
    error: str | None = None
    retry_count: int = 0

    # Meta AI investigation (optional)
    investigation_pending: bool = False
    diagnosis: dict[str, Any] | None = None

    # Persistence
    run_id: str | None = None
    verification_id: str | None = None

    def has_error(self) -> bool:
        return self.error is not None

    def can_proceed(self) -> bool:
        return not self.has_error() and self.step != "complete"

    def next_step(self, step: str) -> None:
        self.step = step