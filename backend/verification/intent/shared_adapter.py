"""Backward-compatible adapter between Person 3 and the shared requirement schema.

Person 3's internal ``VerificationRequirement`` and the canonical
``shared.schemas.requirements.Requirement`` differ in field names and in which
data they consider first-class.  This module is the single conversion point.

Rules:

* The shared contract is **not** modified here.  The adapter lives entirely
  inside ``backend/verification/`` so existing consumers keep working.
* Nothing is invented.  Fields with no canonical counterpart are carried in the
  shared model's ``extensions`` mapping and restored on the way back.
* The shared ``title`` is required where Person 3 has no title.  A short label
  derived from the requirement's own description is used; it is a display
  label, not new evidence.

Conversions:

============================  ======================================
Person 3                      Shared
============================  ======================================
``type``                      ``requirement_type``
``comparison_operator``       ``operator``
``is_mandatory``              ``extensions["p3_is_mandatory"]``
``metadata``                  ``extensions["p3_metadata"]``
``extensions``                ``extensions["p3_extensions"]``
============================  ======================================
"""

from __future__ import annotations

from typing import Any

from backend.verification.exceptions import VerificationError
from backend.verification.models import (
    RequirementSource,
    RequirementType,
    VerificationRequirement,
)
from shared.schemas.requirements import (
    ComparisonOperator,
)
from shared.schemas.requirements import (
    Requirement as SharedRequirement,
)
from shared.schemas.requirements import (
    RequirementSource as SharedRequirementSource,
)
from shared.schemas.requirements import (
    RequirementType as SharedRequirementType,
)

#: Maximum length of a derived display title.
MAX_TITLE_LENGTH = 80


class SharedRequirementAdapterError(VerificationError):
    """Raised when a requirement cannot be represented without data loss."""

    error_code: str = "VERG-040"


def _derived_title(requirement: VerificationRequirement) -> str:
    title = (requirement.metadata or {}).get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    description = (requirement.description or "").strip()
    if description:
        return description.splitlines()[0][:MAX_TITLE_LENGTH]
    return requirement.id


def _confirmation_status(requirement: VerificationRequirement) -> str:
    """Map requirement origin onto the shared confirmation vocabulary.

    Only a developer-confirmed requirement is reported as ``confirmed``;
    inferred origins stay ``proposed`` so an inferred hypothesis can never be
    presented as authoritative.
    """
    if requirement.source is RequirementSource.developer_confirmed:
        return "confirmed"
    return "proposed"


def to_shared_requirement(requirement: VerificationRequirement) -> SharedRequirement:
    """Convert a Person 3 requirement into the canonical shared schema."""
    if not isinstance(requirement, VerificationRequirement):
        raise SharedRequirementAdapterError(
            "to_shared_requirement expects a VerificationRequirement instance.",
            details={"received": type(requirement).__name__},
        )

    operator: ComparisonOperator | None = None
    if requirement.comparison_operator is not None:
        try:
            operator = ComparisonOperator(requirement.comparison_operator)
        except ValueError as exc:
            raise SharedRequirementAdapterError(
                "Unsupported comparison operator for the shared schema.",
                details={"comparison_operator": requirement.comparison_operator},
            ) from exc

    extensions: dict[str, Any] = {
        "p3_is_mandatory": requirement.is_mandatory,
        "p3_metadata": dict(requirement.metadata or {}),
        "p3_extensions": dict(requirement.extensions or {}),
    }

    return SharedRequirement(
        id=requirement.id,
        title=_derived_title(requirement),
        description=requirement.description,
        requirement_type=SharedRequirementType(requirement.type.value),
        source=SharedRequirementSource(requirement.source.value),
        status=_confirmation_status(requirement),
        operator=operator,
        expected_value=requirement.expected_value,
        tolerance=requirement.tolerance,
        extensions=extensions,
    )


def from_shared_requirement(shared: SharedRequirement) -> VerificationRequirement:
    """Convert a canonical shared requirement into a Person 3 requirement."""
    if not isinstance(shared, SharedRequirement):
        raise SharedRequirementAdapterError(
            "from_shared_requirement expects a shared Requirement instance.",
            details={"received": type(shared).__name__},
        )

    extensions = dict(shared.extensions or {})
    metadata = extensions.get("p3_metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    metadata.setdefault("title", shared.title)

    p3_extensions = extensions.get("p3_extensions")
    is_mandatory = extensions.get("p3_is_mandatory")
    if not isinstance(is_mandatory, bool):
        # The shared contract has no mandatory flag.  Confirmed developer
        # intent is treated as blocking; proposed/inferred requirements are not.
        is_mandatory = shared.status == "confirmed"

    return VerificationRequirement(
        id=shared.id,
        description=shared.description,
        source=RequirementSource(shared.source.value),
        type=RequirementType(shared.requirement_type.value),
        expected_value=shared.expected_value,
        comparison_operator=shared.operator.value if shared.operator else None,
        tolerance=shared.tolerance,
        is_mandatory=is_mandatory,
        metadata=metadata,
        extensions=dict(p3_extensions) if isinstance(p3_extensions, dict) else {},
    )


__all__ = [
    "MAX_TITLE_LENGTH",
    "SharedRequirementAdapterError",
    "from_shared_requirement",
    "to_shared_requirement",
]
