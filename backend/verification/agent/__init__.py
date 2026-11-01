"""LangGraph verification workflow: state, nodes, planner, controller.

The authoritative orchestration lives in :mod:`backend.verification.agent.verification_agent`.
The public entry points are :func:`run_verification` (JSON-safe output) and
:func:`run_verification_state` (full terminal state), plus
:class:`VerificationAgentController` for the typed service interface.
"""

from __future__ import annotations

from backend.verification.agent.agent_controller import VerificationAgentController
from backend.verification.agent.agent_state import VerificationState
from backend.verification.agent.verification_agent import (
    build_graph,
    run_verification,
    run_verification_state,
    state_from_mapping,
)

__all__ = [
    "VerificationAgentController",
    "VerificationState",
    "build_graph",
    "run_verification",
    "run_verification_state",
    "state_from_mapping",
]
