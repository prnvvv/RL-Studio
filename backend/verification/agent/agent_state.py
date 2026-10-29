"""Typed state for the RL Studio verification LangGraph workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.verification.models import (
    VerificationInput,
    VerificationContext,
    VerificationCheckResult,
    CheckStatus,
)


@dataclass
class VerificationState:
    """State carried across LangGraph workflow nodes."""

    # Input data
    raw_input: Optional[Dict[str, Any]] = None
    input: Optional[VerificationInput] = None
    context: Optional[VerificationContext] = None

    # Requirement and check state
    requirements: Dict[str, Any] = field(default_factory=dict)
    check_results: Dict[str, VerificationCheckResult] = field(default_factory=dict)
    registered_checks: List[str] = field(default_factory=list)

    # Aggregation and decision
    overall_status: Optional[CheckStatus] = None
    decision_details: str = ""

    # Workflow control
    step: str = "start"  # start, normalizing, planning, checking, aggregating, complete
    error: Optional[str] = None
    retry_count: int = 0

    # Meta AI investigation (optional)
    investigation_pending: bool = False
    diagnosis: Optional[Dict[str, Any]] = None

    # Persistence
    run_id: Optional[str] = None
    verification_id: Optional[str] = None

    def has_error(self) -> bool:
        return self.error is not None

    def can_proceed(self) -> bool:
        return not self.has_error() and self.step != "complete"

    def next_step(self, step: str) -> None:
        self.step = step