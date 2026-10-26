"""Stable component contracts (protocols / interfaces) for the verification subsystem.

These protocols define the contracts that the Meta AI adapter, verification
engine, workflow planner, and downstream consumers depend on.  Implementations
must satisfy these interfaces; the interfaces themselves contain no business
logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from backend.verification.exceptions import chain_error

from backend.verification.models import (
    AgentMetadata,
    VerificationInput,
    VerificationContext,
    VerificationRequirement,
    VerificationPlan,
    VerificationPlanStep,
    VerificationCheckResult,
    VerificationResult,
    VerificationReport,
    EvidenceReference,
    MetricObservation,
    AnomalyObservation,
    CheckStatus,
    RequirementSource,
    RequirementType,
    AnomalyType,
)


# ---------------------------------------------------------------------------
# 1. Meta AI provider interface
# ---------------------------------------------------------------------------


class MetaAIProvider(Protocol):
    """Protocol for a replaceable Meta AI provider adapter.

    Implementations receive a structured request/context and return a typed,
    structured response.  The caller must not assume any particular SDK, model
    name, or endpoint URL — those details are encapsulated by the concrete
    provider class.
    """

    def investigate(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Run an investigation against the given structured request.

        Args:
            request: A dictionary conforming to the provider's expected prompt
                / evidence schema.  Must contain at minimum the fields needed
                for the intended investigation type.

        Returns:
            A dictionary with at least the following keys:
            - "summary": str
            - "observed_facts": List[Dict[str, Any]]
            - "candidate_causes": List[Dict[str, Any]]
            - "supporting_evidence": List[Dict[str, Any]]
            - "contradicting_evidence": List[Dict[str, Any]]
            - "confidence": Optional[float]
            - "root_cause_status": str  # e.g. "confirmed", "probable", "unresolved"
            - "recommended_tests": List[str]
            - "limitations": List[str]

        Raises:
            ProviderTimeoutError: If the provider does not respond within the
                configured timeout.
            ProviderRateLimitError: If the provider rejects the request due to
                rate limiting.
            ProviderRefusalError: If the provider refuses the request.
            ProviderMalformedError: If the provider returns invalid JSON or an
                unexpected schema.
        """
        ...


# ---------------------------------------------------------------------------
# 2. Intent interpretation interface
# ---------------------------------------------------------------------------


class IntentInterpretation(Protocol):
    """Protocol for converting verification input / context into structured
    requirements.

    Implementations take a ``VerificationInput`` (or a subset) and produce a
    sequence of ``VerificationRequirement`` objects together with metadata
    about their source and confirmation status.
    """

    def interpret(
        self,
        input_data: VerificationInput,
        context: VerificationContext,
    ) -> tuple[
        List[VerificationRequirement],
        Dict[str, Any],
    ]:
        """Interpret developer intent and produce structured requirements.

        Args:
            input_data: The verified developer-provided input.
            context: Runtime context linking the input to a run/environment.

        Returns:
            A 2-tuple of:
            - A list of ``VerificationRequirement`` objects, ordered by
              presumed importance.
            - A metadata dictionary with at least the following keys:
                - "source_distribution": Dict[RequirementSource, int]
                  — how many requirements came from each source enum value.
                - "unresolved": List[str] — requirement IDs that could not be
                  fully resolved without additional evidence.
                - "notes": str — free-form remarks (must not contain raw
                  prompts or credentials).
        """
        ...


# ---------------------------------------------------------------------------
# 3. Workflow planner interface
# ---------------------------------------------------------------------------


class WorkflowPlanner(Protocol):
    """Protocol for producing a validated verification plan from structured
    requirements.

    The planner takes a list of ``VerificationRequirement`` objects (typically
    the output of ``IntentInterpretation.interpret``) and produces a
    ``VerificationPlan`` whose steps are ordered, dependency-respecting, and
    tagged with the check tools that should evaluate them.
    """

    def plan(
        self,
        requirements: List[VerificationRequirement],
        context: VerificationContext,
    ) -> VerificationPlan:
        """Generate a verification plan from the given requirements.

        Args:
            requirements: List of requirements from the intent interpreter.
            context: Runtime context for the verification run.

        Returns:
            A ``VerificationPlan`` instance whose ``steps`` are ordered,
            dependency-respecting, and tagged with appropriate
            ``check_tool_id`` values.

        Raises:
            PlanningFailure: If the planner cannot produce a valid plan (e.g.
                circular dependencies, unresolvable requirements).
        """
        ...


# ---------------------------------------------------------------------------
# 3b. Planning failure exception protocol (signalled through the planner)
# ---------------------------------------------------------------------------


class PlanningFailure(Exception):
    """Raised by a ``WorkflowPlanner`` implementation when a valid plan cannot
    be generated.

    Subclasses may add structured detail, but the base class preserves a
    safe, human-readable message.
    """

    def __init__(self, message: str = "Unable to generate a valid verification plan"):
        super().__init__(message)
        self.message = message


# ---------------------------------------------------------------------------
# 4. Verification tool interface
# ---------------------------------------------------------------------------


class VerificationTool(Protocol):
    """Protocol for a registered verification check tool.

    Each tool identifies itself by a stable ``check_tool_id`` string (e.g.
    ``"check_reward_scale"``) and executes a typed check against supplied
    context and arguments.  Tools are registered in a ``ToolRegistry`` and
    invoked by the verification engine or the workflow planner.
    """

    check_tool_id: str

    def execute(
        self,
        context: VerificationContext,
        arguments: Dict[str, Any],
    ) -> VerificationCheckResult:
        """Execute the check against the given context and typed arguments.

        Args:
            context: The verification runtime context (run/environment IDs,
                timestamps, etc.).
            arguments: Typed check-specific arguments.  The schema of this
                dictionary is determined by the concrete tool implementation.
                Tools must validate their own arguments and raise appropriate
                exceptions (e.g. ``InputValidationError``) when they are
                malformed.

        Returns:
            A ``VerificationCheckResult`` indicating pass/fail/unknown/error.

        Raises:
            InputValidationError: If ``arguments`` are malformed or missing
                required fields.
            EvidenceUnavailableError: If the check requires evidence that is
                not present in the context.
            VerificationExecutionError: If the check itself fails to execute
                (e.g. a computational error, not a requirement violation).
        """
        ...


# Concrete base class so tools can inherit shared utility without breaking
# the Protocol contract.  Subclasses only need to implement ``_run_check``.


class _VerificationToolBase:
    """Minimal base class providing a default ``check_tool_id`` property.

    Concrete tools should subclass this and implement ``_run_check`` rather
    than the full ``Protocol`` signature.
    """

    def __init__(self, check_tool_id: str) -> None:
        self.check_tool_id = check_tool_id

    def execute(
        self,
        context: VerificationContext,
        arguments: Dict[str, Any],
    ) -> VerificationCheckResult:
        """Default ``execute`` that validates presence of essential fields and
        delegates to ``_run_check``.

        Tools may override ``execute`` entirely if they need custom argument
        handling, but most should rely on this base implementation.
        """
        # Basic sanity: ensure we have a context
        if context is None:
            from backend.verification.exceptions import InputValidationError

            raise InputValidationError("context must not be None")

        return self._run_check(context, arguments)

    def _run_check(
        self,
        context: VerificationContext,
        arguments: Dict[str, Any],
    ) -> VerificationCheckResult:
        """Concrete tools must implement this method.

        The method must return a ``VerificationCheckResult`` and should not
        raise exceptions that are not ``InputValidationError``,
        ``EvidenceUnavailableError``, or ``VerificationExecutionError``.
        """
        raise NotImplementedError("Subclasses must implement _run_check")


# ---------------------------------------------------------------------------
# 5. Anomaly detector interface
# ---------------------------------------------------------------------------


class AnomalyDetector(Protocol):
    """Protocol for analysing available metric / evidence observations and
    returning typed ``AnomalyObservation`` objects.

    The detector's output is a signal, not proof of a fault.  The verification
    engine must not treat an anomaly score as a confirmed fault without
    supporting deterministic requirement checks.
    """

    def detect(self, observations: List[MetricObservation], context: VerificationContext) -> List[AnomalyObservation]:
        """Detect anomalies from the given metric observations.

        Args:
            observations: Metric observations collected during the training
                run.
            context: Runtime context for the verification run.

        Returns:
            A list of ``AnomalyObservation`` objects.  May be empty if no
            anomalies were detected.

        Raises:
            EvidenceUnavailableError: If the detector requires evidence that
                is not present in the context.
        """
        ...


# ---------------------------------------------------------------------------
# 6. Evidence provider interface
# ---------------------------------------------------------------------------


class EvidenceProvider(Protocol):
    """Protocol for obtaining available evidence for a run or context without
    assuming a particular storage backend.

    Implementations should return structured references (``EvidenceReference``
    objects) rather than raw payloads.  The verification engine and tools should
    work with references; the actual data stays where it is.
    """

    def get_evidence(
        self,
        run_identifier: Optional[str] = None,
        environment_identifier: Optional[str] = None,
        evidence_ids: Optional[List[str]] = None,
    ) -> List[EvidenceReference]:
        """Retrieve evidence references for the given run/environment.

        Args:
            run_identifier: Optional run ID or experiment ID.
            environment_identifier: Optional environment ID / version.
            evidence_ids: Optional list of specific evidence reference IDs to
                retrieve.

        Returns:
            A list of ``EvidenceReference`` objects.  The actual evidence
            payloads must NOT be included; only references (IDs, locations,
                timestamps) are returned.

        Raises:
            EvidenceUnavailableError: If the requested evidence cannot be
                located or accessed.
        """
        ...


# ---------------------------------------------------------------------------
# 7. Verification storage interface
# ---------------------------------------------------------------------------


class VerificationStorage(Protocol):
    """Protocol for persisting and retrieving verification inputs, results,
    and reports using stable identifiers.

    Implementations can be filesystem-based, database-backed, or in-memory
    for testing.  The verification service uses this interface to store
    artefacts without coupling to a specific persistence technology.
    """

    def save_verification_input(
        self,
        input_data: VerificationInput,
        context: Optional[VerificationContext] = None,
    ) -> str:
        """Persist a ``VerificationInput`` and return a stable storage ID.

        Args:
            input_data: The input to persist.
            context: Optional runtime context.

        Returns:
            A storage ID (e.g. a database primary key, a filesystem path) that
            can be used to reload the record.
        """
        ...

    def load_verification_input(self, storage_id: str) -> VerificationInput:
        """Load a previously persisted ``VerificationInput``.

        Args:
            storage_id: The ID returned by ``save_verification_input``.

        Returns:
            The loaded ``VerificationInput`` instance.

        Raises:
            PersistenceError: If the record cannot be found or deserialized.
        """
        ...

    def save_verification_result(self, result: VerificationResult) -> str:
        """Persist a ``VerificationResult`` and return a stable storage ID.

        Args:
            result: The result to persist.

        Returns:
            A storage ID for the persisted record.
        """
        ...

    def load_verification_result(self, storage_id: str) -> VerificationResult:
        """Load a previously persisted ``VerificationResult``.

        Args:
            storage_id: The ID returned by ``save_verification_result``.

        Returns:
            The loaded ``VerificationResult`` instance.

        Raises:
            PersistenceError: If the record cannot be found or deserialized.
        """
        ...

    def save_verification_report(self, report: VerificationReport) -> str:
        """Persist a ``VerificationReport`` and return a stable storage ID.

        Args:
            report: The report to persist.

        Returns:
            A storage ID for the persisted record.
        """
        ...

    def load_verification_report(self, storage_id: str) -> VerificationReport:
        """Load a previously persisted ``VerificationReport``.

        Args:
            storage_id: The ID returned by ``save_verification_report``.

        Returns:
            The loaded ``VerificationReport`` instance.

        Raises:
            PersistenceError: If the record cannot be found or deserialized.
        """
        ...


# ---------------------------------------------------------------------------
# 8. Verification service interface
# ---------------------------------------------------------------------------


class VerificationService(Protocol):
    """Top-level service interface that accepts a verification request and
    returns or retrieves a typed result/report.

    This is the primary entry point for the verification pipeline.  Concrete
    implementations will compose the ``MetaAIProvider``, ``IntentInterpretation``,
    ``WorkflowPlanner``, individual ``VerificationTool`` s, and
    ``VerificationStorage`` to produce a complete investigation cycle.
    """

    def run_verification(
        self,
        input_data: VerificationInput,
        context: VerificationContext,
    ) -> VerificationResult:
        """Execute the full verification pipeline for the given input and
        context.

        The concrete implementation should:
        1. Validate the input.
        2. Optionally call the ``MetaAIProvider`` for intent interpretation
           and workflow planning.
        3. Execute applicable deterministic checks via registered
           ``VerificationTool`` s.
        4. Assemble a ``VerificationResult`` with overall status and per-
           requirement results.
        5. Persist the result via the ``VerificationStorage`` interface.
        6. Return the populated ``VerificationResult``.

        Args:
            input_data: The verification input (agent metadata, configs, intent,
                evidence references).
            context: Runtime context linking the input to a run/environment.

        Returns:
            A ``VerificationResult`` with overall status and per-requirement
            check outcomes.

        Raises:
            InputValidationError: If the input or context is malformed.
            ProviderTimeoutError / ProviderRateLimitError / ProviderRefusalError:
                If the Meta AI provider is involved and fails.
            PersistenceError: If saving the result fails.
        """
        ...


# ---------------------------------------------------------------------------
# Helper: ensure Protocol classes can be used for ``isinstance`` checks
# without triggering import-time side effects.  The ``@runtime_checkable``
# decorator is optional; keep it off unless a concrete use-case requires it.
# ---------------------------------------------------------------------------

# NOTE: ``@runtime_checkable`` is deliberately omitted from the Protocol
# classes above so that imports remain side-effect-free.  If a runtime
# ``isinstance`` check is needed, add it at the call-site rather than at
# module load time.