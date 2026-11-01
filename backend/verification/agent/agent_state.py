"""Typed state for the RL Studio verification LangGraph workflow.

The state is a deliberately small, explicit dataclass.  Every field that a
node reads or writes is declared here so that the workflow contract is
reviewable and testable.  Optional integrations (Meta AI investigation) are
declared as optional fields and never influence the deterministic status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.verification.models import (
    AnomalyObservation,
    CheckStatus,
    VerificationCheckResult,
    VerificationContext,
    VerificationInput,
    VerificationRequirement,
)


@dataclass
class VerificationState:
    """State carried across LangGraph workflow nodes."""

    # Input data
    raw_input: dict[str, Any] | None = None
    input: VerificationInput | None = None
    context: VerificationContext | None = None

    # Requirement and check state
    requirements: list[VerificationRequirement] = field(default_factory=list)
    check_results: dict[str, VerificationCheckResult] = field(default_factory=dict)
    #: Map of requirement ID -> registered check tool ID.
    registered_checks: dict[str, str] = field(default_factory=dict)
    validation_summary: dict[str, Any] = field(default_factory=dict)

    # Aggregation and decision
    overall_status: CheckStatus | None = None
    decision_details: str = ""
    #: Advisory statistical signals; never change the deterministic status.
    anomalies: list[AnomalyObservation] = field(default_factory=list)
    #: Structured consistency summary (problems + contradictions); advisory.
    consistency: dict[str, Any] | None = None

    # Workflow control
    step: str = "start"  # start, normalizing, planning, validating, checking, aggregating, complete
    error: str | None = None
    retry_count: int = 0

    # Meta AI investigation (optional, advisory only).  ``model_client`` is an
    # injected provider implementing ``MetaAIProviderProtocol``; when it is
    # ``None`` no model call is attempted and ``diagnosis`` stays ``None``.
    model_client: Any | None = None
    investigation_pending: bool = False
    diagnosis: dict[str, Any] | None = None
    prompt_version: str | None = None

    # Output
    output: dict[str, Any] | None = None

    # Persistence
    run_id: str | None = None
    verification_id: str | None = None

    def has_error(self) -> bool:
        return self.error is not None

    def can_proceed(self) -> bool:
        return not self.has_error() and self.step != "complete"

    def next_step(self, step: str) -> None:
        self.step = step
