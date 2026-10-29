"""RL Studio verification tools layer.

Provides deterministic verification checks for RL environment configuration,
reward behavior, episode outcomes, events, and metrics.

The tools layer is the approved dispatch mechanism for verification checks
consumed by the LangGraph-based verification agent.  All checkers register
themselves in the global ``tool_registry`` and produce
``VerificationCheckResult`` objects that integrate with the existing
validation, decision, reporting, and persistence modules.

Key design points:
- Single source of truth for tool registration: ``tool_registry.py``.
- Each checker produces ``VerificationCheckResult`` using canonical models.
- No LLM calls in deterministic checkers; model reasoning belongs in the
  agent or intent workflow.
- Evidence provenance is preserved via ``EvidenceReference`` objects.
- Checkers reuse existing models, enums, and interfaces from the verification
  package.
- The LangGraph controller decides workflow progression; the registry
  executes approved checks.

Typical usage::

    from backend.verification.tools import register_check, execute_check, list_checks
    from backend.verification.tools.configuration_checker import execute_check as config_check
    from backend.verification.tools.reward_checker import execute_check as reward_check
    from backend.verification.tools.episode_checker import execute_check as episode_check
    from backend.verification.tools.event_checker import execute_check as event_check
    from backend.verification.tools.metric_checker import execute_check as metric_check

    # Register all check handlers
    register_check("check_config", config_check, description="Configuration verification")
    register_check("check_reward", reward_check, description="Reward verification")
    register_check("check_episode", episode_check, description="Episode outcome verification")
    register_check("check_event", event_check, description="Event verification")
    register_check("check_metric", metric_check, description="Metric threshold verification")

    # List registered checks
    checks = list_checks()

    # Execute a check
    result = execute_check("check_reward", context, {"configured_reward": 100})
"""

from __future__ import annotations


from backend.verification.tools.tool_registry import register_check
from backend.verification.tools.configuration_checker import execute_check as config_check
from backend.verification.tools.reward_checker import execute_check as reward_check
from backend.verification.tools.episode_checker import execute_check as episode_check
from backend.verification.tools.event_checker import execute_check as event_check
from backend.verification.tools.metric_checker import execute_check as metric_check

# Public API names
__all__ = [
    "register_check",
    "execute_check",
    "list_checks",
    "is_check_registered",
    "config_check",
    "reward_check",
    "episode_check",
    "event_check",
    "metric_check",
]

# Shortcut: execute_check is the same as the registry's execute_check
# but also accepts the checker-specific functions via their individual names.

# Ensure the module can be imported without side effects beyond function
# definitions and the harmless exports above.  No API calls, no network
# hooks, no registry mutations occur at module load time.