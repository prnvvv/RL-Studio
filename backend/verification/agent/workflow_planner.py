"""Workflow planner for the RL Studio verification LangGraph workflow.

Translates requirements into a registered-check dispatch plan.
Purely deterministic — no LLM calls required for the base flow.

The requirement-type -> check mapping lives in
``backend.verification.intent.requirement_registry`` so that the planner and
the registry can never disagree about which check evaluates which contract.
"""

from __future__ import annotations

from typing import Any

from backend.verification.intent.requirement_registry import (
    REQUIREMENT_TO_CHECK,
    register_all_checks,
)
from backend.verification.models import VerificationRequirement
from backend.verification.tools.tool_registry import is_check_registered

__all__ = ["REQUIREMENT_TO_CHECK", "plan"]


def plan(
    requirements: list[VerificationRequirement],
    context: Any,
) -> dict[str, str]:
    """Produce a dispatch plan: for each requirement, which check tool ID to use.

    Args:
        requirements: List of VerificationRequirement objects.
        context: VerificationContext (unused in this simple planner; present for
            interface compatibility).

    Returns:
        A dict mapping requirement IDs to check tool IDs.  Requirements whose
        type is not in the mapping are marked with ``"unknown"`` so the caller
        can decide how to handle them (the agent reports them as unevaluable).
    """
    del context  # dispatch is currently context-independent

    registered = {check_id for check_id in REQUIREMENT_TO_CHECK.values() if is_check_registered(check_id)}
    missing = {
        check_id for check_id in REQUIREMENT_TO_CHECK.values() if check_id not in registered
    }
    if missing:
        register_all_checks()
        registered = {
            check_id for check_id in REQUIREMENT_TO_CHECK.values() if is_check_registered(check_id)
        }

    dispatch: dict[str, str] = {}
    for requirement in requirements:
        check_id = REQUIREMENT_TO_CHECK.get(requirement.type.value)
        if check_id is not None and check_id in registered:
            dispatch[requirement.id] = check_id
        else:
            dispatch[requirement.id] = "unknown"
    return dispatch
