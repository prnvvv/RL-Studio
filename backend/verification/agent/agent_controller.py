"""Thin orchestration layer for the verification subsystem.

``VerificationAgentController`` implements the public ``VerificationService``
protocol.  It performs three things and nothing else:

1. validates the typed request objects and converts them into the mapping the
   LangGraph workflow accepts,
2. runs the authoritative workflow (``run_verification_state``) exactly once,
3. converts the terminal state into a typed ``VerificationResult`` and, when a
   store is configured, persists the input and the result.

All verification decisions stay inside the workflow.  The controller never
re-derives a status, never upgrades an outcome, and never calls a model itself.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.verification.agent.verification_agent import run_verification_state
from backend.verification.exceptions import InputValidationError
from backend.verification.models import (
    CheckStatus,
    VerificationContext,
    VerificationInput,
    VerificationReport,
    VerificationResult,
)
from backend.verification.report_builder import build_report, build_summary

logger = logging.getLogger(__name__)


class VerificationAgentController:
    """Concrete ``VerificationService`` backed by the LangGraph workflow.

    Args:
        model_client: Optional provider implementing
            ``investigate(request)``.  When omitted, no model call of any kind
            is attempted and the diagnosis is reported as not requested.
        storage: Optional ``VerificationStorage`` implementation.  When
            omitted, nothing is persisted.
    """

    def __init__(
        self, *, model_client: Any | None = None, storage: Any | None = None
    ) -> None:
        self._model_client = model_client
        self._storage = storage
        self.last_state: Any | None = None

    # -- request handling --------------------------------------------------

    @staticmethod
    def build_raw_input(
        input_data: VerificationInput,
        context: VerificationContext | None = None,
    ) -> dict[str, Any]:
        """Convert typed request objects into the workflow's input mapping.

        Only values that the caller actually supplied are copied; nothing is
        synthesised.  Missing identifiers stay missing so the workflow can
        report them as warnings.
        """
        if not isinstance(input_data, VerificationInput):
            raise InputValidationError(
                "run_verification expects a VerificationInput instance.",
                details={"received": type(input_data).__name__},
            )
        if context is not None and not isinstance(context, VerificationContext):
            raise InputValidationError(
                "run_verification expects a VerificationContext instance or None.",
                details={"received": type(context).__name__},
            )

        raw_input: dict[str, Any] = input_data.model_dump(
            mode="python", exclude_none=True
        )
        if context is not None:
            for key in (
                "run_identifier",
                "environment_identifier",
                "environment_version",
            ):
                value = getattr(context, key, None)
                if value is not None and key not in raw_input:
                    raw_input[key] = value
        return raw_input

    # -- VerificationService ----------------------------------------------

    def run_verification(
        self,
        input_data: VerificationInput,
        context: VerificationContext | None = None,
    ) -> VerificationResult:
        """Execute the workflow once and return a typed verification result."""
        raw_input = self.build_raw_input(input_data, context)

        if self._storage is not None:
            storage_id = self._storage.save_verification_input(input_data, context)
            raw_input.setdefault("storage_id", storage_id)

        state = run_verification_state(raw_input, model_client=self._model_client)
        self.last_state = state

        result = self._to_result(state)
        if self._storage is not None:
            self._storage.save_verification_result(result)
        return result

    def run_verification_output(
        self,
        input_data: VerificationInput,
        context: VerificationContext | None = None,
    ) -> dict[str, Any]:
        """Return the JSON-safe workflow output (including diagnosis)."""
        result = self.run_verification(input_data, context)
        state = self.last_state
        if state is not None and getattr(state, "output", None) is not None:
            return dict(state.output)
        return {
            "overall_status": result.overall_status.value,
            "requirements": {
                requirement_id: check_result.model_dump(mode="json")
                for requirement_id, check_result in result.requirements.items()
            },
            "summary": result.summary,
            "warnings": list(result.warnings),
            "errors": list(result.errors),
        }

    def build_verification_report(
        self,
        result: VerificationResult,
        *,
        diagnosis: dict[str, Any] | None = None,
        recommendations: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> VerificationReport:
        """Build and optionally persist a report for an existing result."""
        report = build_report(
            result,
            diagnosis=diagnosis,
            recommendations=recommendations,
            limitations=limitations,
        )
        if self._storage is not None:
            self._storage.save_verification_report(report)
        return report

    # -- conversion --------------------------------------------------------

    @staticmethod
    def _to_result(state: Any) -> VerificationResult:
        overall = getattr(state, "overall_status", None)
        if not isinstance(overall, CheckStatus):
            overall = CheckStatus.UNKNOWN

        check_results = dict(getattr(state, "check_results", {}) or {})
        evidence_refs: list[str] = []
        for check_result in check_results.values():
            for ref in getattr(check_result, "evidence_refs", []) or []:
                if isinstance(ref, str) and ref and ref not in evidence_refs:
                    evidence_refs.append(ref)

        warnings = list(
            (getattr(state, "validation_summary", {}) or {}).get("warnings") or []
        )
        errors: list[str] = []
        error = getattr(state, "error", None)
        if error:
            errors.append(str(error))

        result = VerificationResult(
            overall_status=overall,
            requirements=check_results,
            evidence_refs=evidence_refs,
            warnings=warnings,
            errors=errors,
        )
        verification_id = getattr(state, "verification_id", None)
        if isinstance(verification_id, str) and verification_id:
            result = result.model_copy(update={"verification_id": verification_id})
        summary = build_summary(result)
        return result.model_copy(update={"summary": summary})


__all__ = ["VerificationAgentController"]
