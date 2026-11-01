"""Compatibility tests for the Person 3 <-> shared requirement adapter."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.verification.intent.shared_adapter import (
    SharedRequirementAdapterError,
    from_shared_requirement,
    to_shared_requirement,
)
from backend.verification.models import (
    RequirementSource,
    RequirementType,
    VerificationRequirement,
)
from shared.schemas.requirements import Requirement as SharedRequirement


def _p3_requirement(**overrides: object) -> VerificationRequirement:
    payload: dict[str, object] = {
        "id": "req_reward_goal",
        "description": "The goal reward must equal 25.",
        "type": RequirementType.reward,
        "expected_value": 25.0,
        "comparison_operator": "==",
        "tolerance": 0.001,
        "source": RequirementSource.developer_confirmed,
        "is_mandatory": True,
        "metadata": {"config_key": "goal_reward", "title": "Goal reward"},
        "extensions": {"run_scope": "warehouse_v1"},
    }
    payload.update(overrides)
    return VerificationRequirement(**payload)


def test_maps_the_renamed_fields_and_preserves_extensions() -> None:
    shared = to_shared_requirement(_p3_requirement())

    assert shared.id == "req_reward_goal"
    assert shared.title == "Goal reward"
    assert shared.requirement_type.value == "reward"
    assert shared.operator is not None and shared.operator.value == "=="
    assert shared.expected_value == 25.0
    assert shared.tolerance == 0.001
    assert shared.status == "confirmed"
    assert shared.extensions["p3_is_mandatory"] is True
    assert shared.extensions["p3_metadata"]["config_key"] == "goal_reward"
    assert shared.extensions["p3_extensions"] == {"run_scope": "warehouse_v1"}


def test_round_trip_preserves_the_person_three_requirement() -> None:
    original = _p3_requirement()

    restored = from_shared_requirement(to_shared_requirement(original))

    assert restored.id == original.id
    assert restored.description == original.description
    assert restored.type is original.type
    assert restored.source is original.source
    assert restored.expected_value == original.expected_value
    assert restored.comparison_operator == original.comparison_operator
    assert restored.tolerance == original.tolerance
    assert restored.is_mandatory == original.is_mandatory
    assert restored.metadata == original.metadata
    assert restored.extensions == original.extensions


def test_derived_title_is_used_when_no_title_is_supplied() -> None:
    shared = to_shared_requirement(
        _p3_requirement(metadata={}, description="The episode must terminate successfully.")
    )

    assert shared.title == "The episode must terminate successfully."


def test_inferred_requirement_is_not_reported_as_confirmed() -> None:
    shared = to_shared_requirement(
        _p3_requirement(source=RequirementSource.code_inferred)
    )

    assert shared.status == "proposed"


def test_shared_requirement_without_person_three_extensions_uses_confirm_status() -> None:
    confirmed = SharedRequirement(
        id="req_shared_1",
        title="Termination",
        description="The episode must terminate.",
        requirement_type="termination",
        status="confirmed",
    )
    proposed = SharedRequirement(
        id="req_shared_2",
        title="Termination (proposed)",
        description="The episode should terminate.",
        requirement_type="termination",
        status="proposed",
    )

    restored_confirmed = from_shared_requirement(confirmed)
    restored_proposed = from_shared_requirement(proposed)

    assert restored_confirmed.is_mandatory is True
    assert restored_confirmed.metadata == {"title": "Termination"}
    assert restored_proposed.is_mandatory is False
    assert restored_proposed.expected_value is None
    assert restored_proposed.comparison_operator is None


def test_shared_schema_is_not_modified_and_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SharedRequirement(
            id="req_extra",
            title="Extra",
            description="Unknown field must be rejected.",
            requirement_type="reward",
            unexpected_field="value",
        )


def test_adapter_rejects_wrong_input_types() -> None:
    with pytest.raises(SharedRequirementAdapterError):
        to_shared_requirement("not-a-requirement")  # type: ignore[arg-type]

    with pytest.raises(SharedRequirementAdapterError):
        from_shared_requirement({"id": "not-a-model"})  # type: ignore[arg-type]
