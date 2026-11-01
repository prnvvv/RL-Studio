"""Validation facades.

The implementations live in the sibling modules
:mod:`backend.verification.result_validator` and
:mod:`backend.verification.consistency_checker`.  They are re-exported here so
callers have one stable import path; no validation logic is duplicated.
"""

from __future__ import annotations

from backend.verification.consistency_checker import (
    check_evidence_consistency,
    check_plan_consistency,
    check_result_consistency,
    check_verification_consistency,
)
from backend.verification.result_validator import (
    INVESTIGATION_REQUIRED_KEYS,
    ROOT_CAUSE_STATUSES,
    validate_anomaly,
    validate_check_result,
    validate_investigation_result,
    validate_requirement_alignment,
    validate_verification_result,
)

__all__ = [
    "INVESTIGATION_REQUIRED_KEYS",
    "ROOT_CAUSE_STATUSES",
    "check_evidence_consistency",
    "check_plan_consistency",
    "check_result_consistency",
    "check_verification_consistency",
    "validate_anomaly",
    "validate_check_result",
    "validate_investigation_result",
    "validate_requirement_alignment",
    "validate_verification_result",
]
