"""Developer-intent parsing and requirement extraction.

Parsing proposes structured requirements from developer text.  A requirement's
``source`` records whether it is developer-confirmed or inferred, and inferred
requirements stay non-authoritative until explicitly confirmed.
"""

from __future__ import annotations

from backend.verification.intent.intent_parser import ParsedIntent, parse_intent
from backend.verification.intent.intent_validator import (
    validate_requirement,
    validate_requirements,
)
from backend.verification.intent.requirement_extractor import extract_requirements
from backend.verification.intent.requirement_registry import (
    REQUIREMENT_TO_CHECK,
    get_check_id,
    register_all_checks,
    verify_registry_consistency,
)

__all__ = [
    "ParsedIntent",
    "REQUIREMENT_TO_CHECK",
    "extract_requirements",
    "get_check_id",
    "parse_intent",
    "register_all_checks",
    "validate_requirement",
    "validate_requirements",
    "verify_registry_consistency",
]
