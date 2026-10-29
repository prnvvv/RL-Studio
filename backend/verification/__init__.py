from __future__ import annotations

# ---------------------------------------------------------------------------
# Core exceptions (re-exported from ``.exceptions`` so they are readily
# importable)
# ---------------------------------------------------------------------------
from .exceptions import (
    EvidenceUnavailableError,
    InputValidationError,
    IntentInterpretationError,
    MetaAIProviderError,
    PersistenceError,
    PlanningError,
    UnsupportedCapabilityError,
    VerificationError,
    VerificationExecutionError,
    chain_error,
)

# ---------------------------------------------------------------------------
# Core interfaces (re-exported from ``.interfaces`` so they are readily
# importable)
# ---------------------------------------------------------------------------
from .interfaces import (
    AnomalyDetector,
    EvidenceProvider,
    IntentInterpretation,
    MetaAIProvider,
    PlanningFailure,
    VerificationService,
    VerificationStorage,
    VerificationTool,
    WorkflowPlanner,
    _VerificationToolBase,
)

# ---------------------------------------------------------------------------
# Core models (re-exported from ``.models`` so they are readily importable)
# ---------------------------------------------------------------------------
from .models import (
    AgentMetadata,
    AnomalyObservation,
    AnomalyType,
    CheckStatus,
    EvidenceReference,
    MetricObservation,
    RequirementSource,
    RequirementType,
    VerificationCheckResult,
    VerificationContext,
    VerificationInput,
    VerificationPlan,
    VerificationPlanStep,
    VerificationReport,
    VerificationRequirement,
    VerificationResult,
)

# ---------------------------------------------------------------------------
# Public API symbols — explicitly listed so ``__all__`` is meaningful.
# ---------------------------------------------------------------------------
__all__ = [
    # Models
    "AgentMetadata",
    "VerificationInput",
    "VerificationContext",
    "VerificationRequirement",
    "VerificationPlan",
    "VerificationPlanStep",
    "VerificationCheckResult",
    "VerificationResult",
    "VerificationReport",
    "EvidenceReference",
    "MetricObservation",
    "AnomalyObservation",
    "CheckStatus",
    "RequirementSource",
    "RequirementType",
    "AnomalyType",
    # Interfaces
    "MetaAIProvider",
    "IntentInterpretation",
    "WorkflowPlanner",
    "VerificationTool",
    "AnomalyDetector",
    "EvidenceProvider",
    "VerificationStorage",
    "VerificationService",
    "_VerificationToolBase",
    "PlanningFailure",
    "chain_error",
    # Exceptions
    "VerificationError",
    "InputValidationError",
    "IntentInterpretationError",
    "PlanningError",
    "UnsupportedCapabilityError",
    "EvidenceUnavailableError",
    "VerificationExecutionError",
    "MetaAIProviderError",
    "PersistenceError",
]

# ---------------------------------------------------------------------------
# NOTE: Deliberately do NOT import from sub-modules that have side effects
# (e.g. test registries, initialisation side‑effects).  Those should be
# imported by the consumer only when explicitly needed.
# ---------------------------------------------------------------------------
