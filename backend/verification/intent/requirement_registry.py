"""Requirement registry — maps requirement types to their registered checker
implementations.

This is the single authoritative registry that the workflow planner consults
when dispatching checks.  It must agree with the REQUIREMENT_TO_CHECK mapping
in workflow_planner.py and the checker signatures in the tools package.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.verification.models import RequirementType
from backend.verification.tools.tool_registry import is_check_registered


# ---------------------------------------------------------------------------
# Canonical mapping: requirement type -> check tool identifier
# ---------------------------------------------------------------------------

REQUIREMENT_TO_CHECK: Dict[str, str] = {
    "reward": "check_reward",
    "termination": "check_episode",
    "event": "check_event",
    "metric": "check_metric",
    "configuration": "check_config",
}


def get_check_id(requirement_type: RequirementType) -> Optional[str]:
    """Return the registered check tool ID for a given requirement type.

    Args:
        requirement_type: The RequirementType enum value.

    Returns:
        The check tool identifier string, or None if no checker is registered.
    """
    return REQUIREMENT_TO_CHECK.get(requirement_type.value)


def verify_registry_consistency() -> List[str]:
    """Check that the registry agrees with declared check handlers.

    Returns a list of warning strings; empty means consistent.
    """
    warnings: List[str] = []
    for req_type, check_id in REQUIREMENT_TO_CHECK.items():
        registered = is_check_registered(check_id)
        if not registered:
            warnings.append(
                f"Registry maps '{req_type}' -> '{check_id}' but check is "
                "not registered in tool_registry"
            )
    return warnings


def register_all_checks() -> List[str]:
    """Ensure all checks in the registry are registered in the tool registry.

    Returns a list of registration actions taken.
    """
    from backend.verification.tools import (
        configuration_checker,
        reward_checker,
        episode_checker,
        event_checker,
        metric_checker,
    )

    actions: List[str] = []
    handlers: Dict[str, Any] = {
        "check_reward": reward_checker.execute_check,
        "check_episode": episode_checker.execute_check,
        "check_event": event_checker.execute_check,
        "check_metric": metric_checker.execute_check,
        "check_config": configuration_checker.execute_check,
    }

    for check_id, handler in handlers.items():
        already = is_check_registered(check_id)
        if not already:
            from backend.verification.tools.tool_registry import register_check
            register_check(check_id, handler, description=f"Registered {check_id}")
            actions.append(f"Registered {check_id}")

    return actions