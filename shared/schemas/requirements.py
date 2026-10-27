"""Canonical requirement / contract model (AGENTS.md §7.3).

A :class:`Requirement` records what the developer confirmed the system must do,
separating *confirmed intent* from *inferred hypothesis*.  A hard violation
must name the active rule and carry evidence (see
``shared.schemas.events.RequirementViolationEvent``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from . import SCHEMA_VERSION, new_uuid


class RequirementSource(str, Enum):
    developer_confirmed = "developer_confirmed"
    test_derived = "test_derived"
    code_inferred = "code_inferred"
    documentation_inferred = "documentation_inferred"
    system_invariant = "system_invariant"


class RequirementType(str, Enum):
    reward = "reward"
    termination = "termination"
    observation = "observation"
    action_space = "action_space"
    grid_goal = "grid_goal"
    collision = "collision"
    metric = "metric"
    configuration = "configuration"


class ComparisonOperator(str, Enum):
    EQ = "=="
    NEQ = "!="
    GTE = ">="
    LTE = "<="
    GT = ">"
    LT = "<"


class Requirement(BaseModel):
    """A single, versioned, developer-confirmed (or inferred) requirement.

    ``expected_value`` may be a scalar, range, or other structure depending on
    ``requirement_type``.  When ``tolerance`` is set it is an absolute
    tolerance applied to numeric equality/range comparisons.
    """

    id: str = Field(default_factory=new_uuid, description="Stable requirement ID.")
    version: str = Field(default="1", description="Requirement version string.")
    schema_version: str = Field(default=SCHEMA_VERSION)
    title: str = Field(description="Short name for the requirement.")
    description: str = Field(description="Human-readable statement of intent.")
    requirement_type: RequirementType
    source: RequirementSource = Field(default=RequirementSource.developer_confirmed)
    status: str = Field(
        default="confirmed",
        description="Confirmation status: 'confirmed', 'proposed', 'deprecated'.",
    )
    operator: Optional[ComparisonOperator] = Field(
        default=None, description="Comparison operator when the requirement checks a value."
    )
    expected_value: Any = Field(
        default=None,
        description=(
            "Expected value, range, or set for the requirement. Absent when the "
            "requirement is purely structural."
        ),
    )
    tolerance: Optional[float] = Field(
        default=None, ge=0, description="Absolute tolerance for numeric comparisons."
    )
    environment_version: Optional[str] = Field(
        default=None, description="Environment version the requirement applies to, if scoped."
    )
    agent_config_fingerprint: Optional[str] = Field(
        default=None, description="Agent config fingerprint the requirement applies to, if scoped."
    )
    created_at: Optional[datetime] = Field(
        default=None,
        description="UTC creation timestamp (timezone-aware). Left None by default "
        "for deterministic tests; call sites that need it use a factory.",
    )
    confirmed_by: Optional[str] = Field(
        default=None, description="Identifier of the confirmer (developer, test id, ...)."
    )
    created_by: Optional[str] = None
    change_history: List[Dict[str, Any]] = Field(default_factory=list)
    extensions: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True, "extra": "forbid"}


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp (re-exported for call sites)."""
    return datetime.now(timezone.utc)
