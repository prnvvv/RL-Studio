"""Main verification LangGraph workflow.

Connects the existing verification modules into a single bounded workflow.
LangGraph is the sole authoritative orchestrator; no competing loop exists.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from langgraph.graph import StateGraph
from langgraph.constants import END
from langgraph.checkpoint.memory import MemorySaver

from backend.verification.agent.agent_state import VerificationState
from backend.verification.agent.workflow_planner import plan as plan_checks
from backend.verification.agent.decision_engine import decide, aggregate_results
from backend.verification.input.input_adapter import adapt_input
from backend.verification.input.context_builder import build_context
from backend.verification.input.schema_normalizer import normalise_verification_input
from backend.verification.tools.tool_registry import execute_check, list_checks

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def node_normalize(input_data: Dict[str, Any], state: VerificationState) -> VerificationState:
    """Normalize and validate the raw verification input."""
    try:
        normalised = normalise_verification_input(input_data)
        from backend.verification.models import VerificationInput
        vi = VerificationInput(**normalised)
        state.input = vi
    except Exception as exc:
        state.error = f"Input normalization failed: {exc}"
        state.step = "complete"
        return state

    # Build runtime context
    try:
        from backend.verification.input.context_builder import build_context
        ctx = build_context(vi)
        state.context = ctx
    except Exception as exc:
        state.error = f"Context building failed: {exc}"
        state.step = "complete"
        return state

    state.step = "planning"
    return state


def node_plan(state: VerificationState) -> VerificationState:
    """Produce a dispatch plan mapping requirements to check tools."""
    if state.input is None:
        state.error = "No input data to plan from."
        state.step = "complete"
        return state

    # Extract requirements from the verified input.
    # For now, we use a simple heuristic: inspect the developer intent
    # and create minimal requirements.  In a full implementation, this
    # would be replaced by the intent parser / extractor.
    reqs: List[Any] = []
    if state.input.developer_intent:
        # Minimal: create one requirement per known type found in intent.
        # This is a placeholder; the intent parser will be integrated later.
        pass

    # If no requirements extracted, create a default reward check.
    if not reqs:
        from backend.verification.models import VerificationRequirement, RequirementType
        req = VerificationRequirement(
            description="agent should achieve expected reward",
            type=RequirementType.reward,
            expected_value=None,
        )
        reqs.append(req)

    # Produce dispatch plan
    plan_result = plan_checks(reqs, state.context)
    state.registered_checks = list(plan_result.values())

    state.step = "checking"
    return state


def node_check(state: VerificationState) -> VerificationState:
    """Execute registered deterministic checks and collect results."""
    if state.input is None or state.context is None:
        state.error = "Missing input or context for check execution."
        state.step = "complete"
        return state

    state.check_results = {}

    for req_id, check_tool_id in state.registered_checks.items():
        # Get the requirement for this ID (placeholder lookup).
        # In a full implementation, this would map back to the actual
        # VerificationRequirement object.
        from backend.verification.models import VerificationRequirement, RequirementType
        # Determine configured/observed values from context/input for the check.
        # For now, pass minimal arguments; each checker knows how to handle
        # missing evidence.
        req = VerificationRequirement(
            description=f"check:{check_tool_id}",
            type=RequirementType.reward,  # placeholder
            expected_value=None,
        )

        try:
            # Execute the check through the registry.
            # The arguments dict is checker-specific; we supply a minimal
            # set and let the checker handle missing data gracefully.
            args: Dict[str, Any] = {}
            # Try to extract relevant config/evidence from context/input
            # If the check cannot run with the available data, it will return
            # UNKNOWN/ERROR appropriately.
            result = execute_check(
                check_tool_id,
                state.context,
                {"requirement": req, **(args or {})},
            )
            state.check_results[req_id] = result
        except Exception as exc:
            logger.error(f"Check {check_tool_id} failed: {exc}")
            state.check_results[req_id] = type(
                "CheckResult", (), {"status": CheckStatus.ERROR, "details": str(exc)}
            )()

    # Move to aggregation regardless of individual check outcomes.
    state.step = "aggregating"
    return state


def node_aggregate(state: VerificationState) -> VerificationState:
    """Aggregate per-requirement check results into an overall status."""
    if not state.check_results:
        state.overall_status = CheckStatus.UNKNOWN
        state.decision_details = "No check results to aggregate."
        state.step = "complete"
        return state

    aggregated = aggregate_results(state.check_results)
    state.overall_status = aggregated["overall_status"]
    state.decision_details = aggregated["details"]

    # If Meta AI investigation is desired for inconclusive cases,
    # set a flag here.  For Phase 1, we skip the AI layer.
    if state.overall_status in {CheckStatus.UNKNOWN, CheckStatus.ERROR}:
        # Check if we have enough evidence to possibly proceed
        # or if we should stop with the deterministic result.
        pass

    state.step = "complete"
    return state


def node_complete(state: VerificationState) -> VerificationState:
    """Final node — output the structured verification result."""
    # Build the final output dict
    output: Dict[str, Any] = {
        "overall_status": state.overall_status,
        "details": state.decision_details,
        "requirements": {
            rid: {"status": cr.status, "expected": cr.expected, "actual": cr.actual}
            for rid, cr in state.check_results.items()
        },
    }

    # Attach context-derived identifiers if available
    if state.context is not None:
        output["run_identifier"] = state.context.run_identifier
        output["environment_identifier"] = state.context.environment_identifier
        output["environment_version"] = state.context.environment_version

    state.step = "complete"
    return state


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph() -> Any:
    """Build and return the LangGraph StateGraph for verification."""
    workflow = StateGraph(VerificationState)

    # Add nodes
    workflow.add_node("normalize", node_normalize)
    workflow.add_node("plan", node_plan)
    workflow.add_node("check", node_check)
    workflow.add_node("aggregate", node_aggregate)
    workflow.add_node("complete", node_complete)

    # Define edges (linear progression with conditional branching)
    workflow.set_entry_point("normalize")

    workflow.add_edge("normalize", "plan")
    workflow.add_edge("plan", "check")
    workflow.add_edge("check", "aggregate")
    workflow.add_edge("aggregate", "complete")
    workflow.add_edge("complete", END)

    # Add explicit terminal handling for errors
    # (LangGraph will naturally END if we reach END from complete)

    # Compile with memory for persistence across runs
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)

    return app


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_verification(
    raw_input: Dict[str, Any],
    *,
    model_api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full verification pipeline from raw input.

    Args:
        raw_input: Developer-provided verification input dict.
        model_api_key: Optional Meta API key (not used in Phase 1 deterministic
            mode; provided for interface compatibility).

    Returns:
        A dict with ``overall_status``, per-requirement results, and
        ``details`` string.
    """
    app = build_graph()

    # Initial state
    initial_state = VerificationState(raw_input=raw_input)

    # Run the graph
    try:
        result_state = app.invoke(initial_state)
    except Exception as exc:
        logger.error(f"Verification graph execution failed: {exc}")
        return {
            "overall_status": "error",
            "details": f"Verification graph execution failed: {exc}",
            "requirements": {},
        }

    # Extract the final output
    output: Dict[str, Any] = {
        "overall_status": result_state.overall_status,
        "details": result_state.decision_details,
        "requirements": {
            rid: {
                "status": cr.status if hasattr(cr, "status") else str(cr.get("status", "unknown")),
                "expected": getattr(cr, "expected", None),
                "actual": getattr(cr, "actual", None),
            }
            for rid, cr in result_state.check_results.items()
        },
    }

    if result_state.context is not None:
        output["run_identifier"] = result_state.context.run_identifier
        output["environment_identifier"] = result_state.context.environment_identifier
        output["environment_version"] = result_state.context.environment_version

    return output