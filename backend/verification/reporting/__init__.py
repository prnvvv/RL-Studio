"""Reporting facades.

The report assembly lives in :mod:`backend.verification.report_builder` and
serialisation in :mod:`backend.verification.result_serializer`.  They are
re-exported here for a single stable import path.
"""

from __future__ import annotations

from backend.verification.report_builder import build_report, build_summary
from backend.verification.result_serializer import (
    check_status_value,
    serialize_check_result,
    serialize_requirements,
    serialize_verification_output,
    to_jsonable,
)

__all__ = [
    "build_report",
    "build_summary",
    "check_status_value",
    "serialize_check_result",
    "serialize_requirements",
    "serialize_verification_output",
    "to_jsonable",
]
