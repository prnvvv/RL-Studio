"""Workflow planner for the RL Studio verification LangGraph workflow.

Translates requirements into a registered-check dispatch plan.
Purely deterministic — no LLM calls required for the base flow.
"""

from __future__ import annotations

from typing import Any

from backend.verification.models import VerificationRequirement
from backend.verification.tools import (
    configuration_checker,
    episode_checker,
    event_checker,
    metric_checker,
    reward_checker,
)
from backend.verification.tools.tool_registry import (
    is_check_registered,
    register_check,
)

# Mapping from requirement type to registered check identifier.
# This table can be extended as new requirement types and checks are added.
REQUIREMENT_TO_CHECK: dict[str, str] = {
    "reward": "check_reward",
    "termination": "check_episode",
    "event": "check_event",
    "metric": "check_metric",
    "configuration": "check_config",
}


def plan(
    requirements: list[VerificationRequirement],
    context: Any,
) -> dict[str, list[str]]:
    """Produce a dispatch plan: for each requirement, which check tool ID to use.

    Args:
        requirements: List of VerificationRequirement objects.
        context: VerificationContext (unused in this simple planner; present for
            interface compatibility).

    Returns:
        A dict mapping requirement IDs to check tool IDs.  Requirements whose
        type is not in the mapping are marked with ``"unknown"`` so the caller
        can decide how to handle them.
    """
    plan: dict[str, str] = {}
    for req in requirements:
        check_id = REQUIREMENT_TO_CHECK.get(req.type.value)
        if check_id is not None:
            # Ensure the check is registered; if not, register it lazily.
            if not is_check_registered(check_id):
                _auto_register(check_id)
            plan[req.id] = check_id
        else:
            plan[req.id] = "unknown"
    return plan


def _auto_register(check_id: str) -> None:
    """Register a check handler based on its identifier.

    This keeps the registry populated without requiring manual registration
    of every check at startup.
    """

    # Map check IDs to their handler functions.
    _HANDLERS: dict[str, Any] = {
        "check_reward": reward_checker.execute_check,
        "check_episode": episode_checker.execute_check,
        "check_event": event_checker.execute_check,
        "check_metric": metric_checker.execute_check,
        "check_config": configuration_checker.execute_check,
    }

    handler = _HANDLERS.get(check_id)
    if handler is not None:
        register_check(check_id, handler, description=f"Auto-registered {check_id}")