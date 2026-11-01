"""Dedicated tests for the intent requirement validator.

Statuses/unsupported forms are asserted explicitly so a requirement can never
silently become authoritative merely because it parsed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from backend.verification.intent.intent_validator import (
    validate_requirement,
    validate_requirements,
)
from backend.verification.models import (
    RequirementSource,
    RequirementType,
    VerificationRequirement,
)


def _requirement(**overrides: object) -> VerificationRequirement:
    payload: dict[str, object] = {
        "id": "req_test",
        "description": "goal reward == 25",
        "type": RequirementType.reward,
        "expected_value": 25,
        "comparison_operator": "==",
        "source": RequirementSource.developer_confirmed,
    }
    payload.update(overrides)
    return VerificationRequirement(**payload)


def test_valid_reward_requirement_passes_validation() -> None:
    is_valid, errors = validate_requirement(_requirement())

    assert is_valid is True
    assert errors == []


def test_valid_termination_requirement_without_expected_value_is_supported() -> None:
    is_valid, errors = validate_requirement(
        _requirement(
            type=RequirementType.termination,
            description="the episode must terminate successfully",
            expected_value=None,
            comparison_operator=None,
        )
    )

    assert is_valid is True
    assert errors == []


def test_reward_requirement_without_expected_value_is_invalid() -> None:
    is_valid, errors = validate_requirement(
        _requirement(expected_value=None, description="goal reward must equal the goal value")
    )

    assert is_valid is False
    assert [error.error_type for error in errors] == ["missing_expected_value"]
    assert errors[0].req_id == "req_test"


def test_vague_reward_is_left_for_the_parser_to_reject() -> None:
    # The parser flags vague language; the validator must not invent a value.
    is_valid, errors = validate_requirement(
        _requirement(expected_value=None, description="the reward should be high")
    )

    assert is_valid is True
    assert errors == []


def test_unsupported_requirement_type_is_rejected() -> None:
    is_valid, errors = validate_requirement(
        _requirement(type=RequirementType.observation, expected_value="shape")
    )

    assert is_valid is False
    assert len(errors) == 1
    assert errors[0].error_type == "unsupported_type"


def test_metric_requirement_without_expected_value_is_invalid() -> None:
    is_valid, errors = validate_requirement(
        _requirement(
            type=RequirementType.metric,
            expected_value=None,
            comparison_operator=">=",
        )
    )

    assert is_valid is False
    assert [error.error_type for error in errors] == ["missing_expected_value"]


def test_configuration_requirement_is_valid_with_expected_value() -> None:
    is_valid, errors = validate_requirement(
        _requirement(
            type=RequirementType.configuration,
            expected_value=0.001,
            description="learning rate == 0.001",
        )
    )

    assert is_valid is True
    assert errors == []


def test_malformed_requirement_input_is_rejected_by_the_model() -> None:
    with pytest.raises(PydanticValidationError):
        _requirement(comparison_operator="~")


def test_validate_requirements_summarises_valid_and_invalid_requirements() -> None:
    summary = validate_requirements(
        [
            _requirement(id="req_valid"),
            _requirement(id="req_invalid", expected_value=None),
        ]
    )

    assert summary["total"] == 2
    assert summary["valid"] == 1
    assert summary["invalid"] == 1
    assert set(summary["errors"]) == {"req_invalid"}
    assert summary["errors"]["req_invalid"][0]["type"] == "missing_expected_value"


def test_empty_requirement_list_is_a_valid_empty_summary() -> None:
    summary = validate_requirements([])

    assert summary["valid"] == 0
    assert summary["invalid"] == 0
    assert summary["errors"] == {}
