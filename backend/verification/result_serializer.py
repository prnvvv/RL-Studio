"""Serialisation of verification results into JSON-safe payloads.

The verification workflow keeps canonical Pydantic models internally.  API
handlers, storage adapters, and the UI must receive plain JSON-compatible
values, including the contract-status vocabulary defined in
``backend.verification.status_mapping``.

Rules:
* Enum members are serialised by value, never by ``repr``.
* Datetimes are ISO-8601 UTC strings.
* Unknown objects are converted through their ``model_dump`` when available,
  otherwise through ``str`` — never silently dropped.
* No fabricated fields: a value that was ``None`` stays ``None``.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from backend.verification.models import (
    CheckStatus,
    VerificationCheckResult,
    VerificationRequirement,
)
from backend.verification.status_mapping import to_contract_status


def to_jsonable(value: Any) -> Any:
    """Recursively convert *value* into JSON-serialisable primitives."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return to_jsonable(dump())
    return str(value)


def check_status_value(status: CheckStatus | str) -> str:
    """Return the canonical string value of a check status."""
    return status.value if isinstance(status, CheckStatus) else str(status)


def serialize_check_result(result: VerificationCheckResult) -> dict[str, Any]:
    """Serialise a single ``VerificationCheckResult``.

    ``contract_status`` is added additively so consumers can use the
    repository-wide ``pass`` / ``violation`` / ``not_evaluable`` /
    ``inconclusive`` vocabulary without losing the internal status lattice.
    """
    status = result.status
    return {
        "requirement_id": result.requirement_id,
        "status": check_status_value(status),
        "contract_status": to_contract_status(status),
        "expected": to_jsonable(result.expected),
        "actual": to_jsonable(result.actual),
        "tolerance": result.tolerance,
        "evidence_refs": list(result.evidence_refs),
        "is_mandatory": result.is_mandatory,
        "timestamp": to_jsonable(result.timestamp),
        "details": to_jsonable(result.details or {}),
    }


def serialize_requirements(
    requirements: list[VerificationRequirement],
) -> list[dict[str, Any]]:
    """Serialise the requirement set that was evaluated."""
    payload: list[dict[str, Any]] = []
    for requirement in requirements:
        payload.append(
            {
                "id": requirement.id,
                "description": requirement.description,
                "type": to_jsonable(requirement.type),
                "source": to_jsonable(requirement.source),
                "expected_value": to_jsonable(requirement.expected_value),
                "comparison_operator": requirement.comparison_operator,
                "tolerance": requirement.tolerance,
                "is_mandatory": requirement.is_mandatory,
                "metadata": to_jsonable(requirement.metadata),
            }
        )
    return payload


def serialize_verification_output(
    *,
    overall_status: CheckStatus,
    check_results: dict[str, VerificationCheckResult],
    requirements: list[VerificationRequirement] | None = None,
    details: str = "",
    run_identifier: str | None = None,
    environment_identifier: str | None = None,
    environment_version: str | None = None,
    verification_id: str | None = None,
    agent_id: str | None = None,
    step: str = "complete",
    error: str | None = None,
    warnings: list[str] | None = None,
    diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the public, JSON-safe verification output payload."""
    requirements_payload = {
        requirement_id: serialize_check_result(result)
        for requirement_id, result in check_results.items()
    }
    output: dict[str, Any] = {
        "overall_status": check_status_value(overall_status),
        "contract_status": to_contract_status(overall_status),
        "details": details,
        "requirements": requirements_payload,
        "requirement_definitions": serialize_requirements(requirements or []),
        "warnings": list(warnings or []),
        "step": step,
    }
    if verification_id is not None:
        output["verification_id"] = verification_id
    if run_identifier is not None:
        output["run_identifier"] = run_identifier
    if environment_identifier is not None:
        output["environment_identifier"] = environment_identifier
    if environment_version is not None:
        output["environment_version"] = environment_version
    if agent_id is not None:
        output["agent_id"] = agent_id
    if error is not None:
        output["error"] = error
    if diagnosis is not None:
        output["diagnosis"] = to_jsonable(diagnosis)
    return output


__all__ = [
    "check_status_value",
    "serialize_check_result",
    "serialize_requirements",
    "serialize_verification_output",
    "to_jsonable",
]
