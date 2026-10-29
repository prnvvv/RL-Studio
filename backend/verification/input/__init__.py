from __future__ import annotations

from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Public API symbols — explicitly listed so ``__all__`` is meaningful.
# ---------------------------------------------------------------------------

# Input adapter entry point
from .input_adapter import adapt_input, adapt_from_parts  # noqa: F401

# Context builder entry point
from .context_builder import build_context, assemble_input  # noqa: F401

# Schema normaliser helpers
from .schema_normalizer import (
    normalise_verification_input,
    normalise_agent_metadata,
    normalise_environment_config,
    normalise_training_config,
    normalise_developer_intent,
    normalise_execution_evidence,
    _normalize_optional_string,
    _normalize_timestamp,
)  # noqa: F401

# ---------------------------------------------------------------------------
# Public API symbols — exported via __all__
# ---------------------------------------------------------------------------

__all__ = [
    # Adapter
    "adapt_input",
    "adapt_from_parts",
    # Context builder
    "build_context",
    "assemble_input",
    # Schema normalisation
    "normalise_verification_input",
    "normalise_agent_metadata",
    "normalise_environment_config",
    "normalise_training_config",
    "normalise_developer_intent",
    "normalise_execution_evidence",
    "_normalize_optional_string",
    "_normalize_timestamp",
]

# ---------------------------------------------------------------------------
# NOTE: Deliberately do NOT import from sub-modules that have side effects
# (e.g. test registries, initialisation side‑effects).  Those should be
# imported by the consumer only when explicitly needed.
# ---------------------------------------------------------------------------
# NOTE: No circular imports are introduced.  All imports are resolved at
# function-call time, not at module load time, except for the canonical
# types (VerificationInput, VerificationContext) which are safe to import
# at the top level because they are pure Pydantic models.
# ---------------------------------------------------------------------------
