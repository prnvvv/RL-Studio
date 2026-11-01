"""Requirement extractor — converts parsed intent into VerificationRequirement
objects, preserving source text and correct types.

Each parsed constraint from the intent parser becomes an independent
VerificationRequirement with a stable UUID, the correct type, and exact
expected values.
"""

from __future__ import annotations

import uuid
from typing import Any

from backend.verification.models import (
    RequirementSource,
    RequirementType,
    VerificationRequirement,
)


def extract_requirements(
    parsed: object,
) -> list[VerificationRequirement]:
    """Convert a parsed intent result into a list of VerificationRequirement objects.

    Args:
        parsed: A ParsedIntent instance (or dict) returned by
            ``intent_parser.parse_intent``.

    Returns:
        A list of VerificationRequirement, one per deterministically extracted
        constraint.  Unsupported or ambiguous intents produce an empty list;
        the caller should treat the result as ``unsupported=True``.
    """
    if not isinstance(parsed, dict):
        return []

    requirements: list[VerificationRequirement] = []
    original_text: str = parsed.get("original_text", "")
    requirements_data: list[dict[str, Any]] = parsed.get("requirements", [])

    for rd in requirements_data:
        metadata: dict[str, Any] = {"original_intent": original_text}
        # Constraint-level metadata from the parser (``required_event``,
        # ``forbidden_event``, ``config_key``, ``max_steps``) is carried through
        # unchanged; ``None`` values are dropped so that a checker never receives
        # an explicit "no constraint" in place of an absent key.
        raw_metadata = rd.get("metadata")
        if isinstance(raw_metadata, dict):
            for key, value in raw_metadata.items():
                if value is not None:
                    metadata[str(key)] = value

        source = RequirementSource.code_inferred
        raw_source = rd.get("source")
        if isinstance(raw_source, str):
            try:
                source = RequirementSource(raw_source)
            except ValueError:
                source = RequirementSource.code_inferred

        req = VerificationRequirement(
            id=str(uuid.uuid4()),
            description=rd.get("description", "requirement extracted from intent"),
            source=source,
            type=RequirementType(rd["type"]),
            expected_value=rd.get("expected_value"),
            comparison_operator=rd.get("comparison_operator"),
            tolerance=rd.get("tolerance"),
            is_mandatory=True,
            metadata=metadata,
        )
        requirements.append(req)

    return requirements