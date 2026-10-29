"""Requirement extractor — converts parsed intent into VerificationRequirement
objects, preserving source text and correct types.

Each parsed constraint from the intent parser becomes an independent
VerificationRequirement with a stable UUID, the correct type, and exact
expected values.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from backend.verification.models import (
    RequirementSource,
    RequirementType,
    VerificationRequirement,
)


def extract_requirements(
    parsed: object,
) -> List[VerificationRequirement]:
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

    requirements: List[VerificationRequirement] = []
    original_text: str = parsed.get("original_text", "")
    requirements_data: List[Dict[str, Any]] = parsed.get("requirements", [])

    for rd in requirements_data:
        req = VerificationRequirement(
            id=str(uuid.uuid4()),
            description=rd.get("description", "requirement extracted from intent"),
            source=RequirementSource.code_inferred,
            type=RequirementType(rd["type"]),
            expected_value=rd.get("expected_value"),
            comparison_operator=rd.get("comparison_operator"),
            tolerance=None,
            is_mandatory=True,
            metadata={"original_intent": original_text},
        )
        requirements.append(req)

    return requirements