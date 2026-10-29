"""Main verification LangGraph workflow.

Connects the existing verification modules into a single bounded workflow.
LangGraph is the sole authoritative orchestrator; no competing loop exists.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph
from langgraph.constants import END

from backend.verification.agent.agent_state import VerificationState
from backend.verification.agent.workflow_planner import plan as plan_checks
from backend.verification.agent.decision_engine import aggregate_results, CheckStatus
from backend.verification.input.input_adapter import adapt_input
from backend.verification.input.context_builder import build_context
from backend.verification.input.schema_normalizer import normalise_verification_input
from backend.verification.tools.tool_registry import execute_check, list_checks, is_check_registered
from backend.verification.models import RequirementType

from backend.verification.tools import (
    configuration_checker,
    reward_checker,
    episode_checker,
    event_checker,
    metric_checker,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def node_normalize(state: VerificationState) -> VerificationState:
    """Normalize and validate the raw verification input.

    Reads ``state.raw_input``, normalises it through the schema normaliser,
    and wraps the result in a ``VerificationInput``.  Any normalisation error
    is recorded as a state error and the workflow stops.
    """
    raw_input = getattr(state, "raw_input", None)
    if raw_input is None:
        state.error = "No raw input available for normalisation."
        state.step = "complete"
        return state

    try:
        normalised = normalise_verification_input(raw_input)
        from backend.verification.models import VerificationInput
        vi = VerificationInput(**normalised)
        state.input = vi
    except Exception as exc:
        state.error = f"Input normalization failed: {exc}"
        state.step = "complete"
        return state

    # Build runtime context from the verified input
    try:
        ctx = build_context(state.input)
        state.context = ctx
    except Exception as exc:
        state.error = f"Context building failed: {exc}"
        state.step = "complete"
        return state

    state.step = "planning"
    return state


def node_plan(state: VerificationState) -> VerificationState:
    """Produce a dispatch plan mapping requirements to check tools.

    Uses the intent parser to extract structured requirements from the
    developer intent, then maps them to check tool IDs via the planner.
    If no requirements can be derived, the workflow stops with an
    informative status rather than silently injecting default checks.

    The created requirements are stored in ``state.requirements`` so that
    they can be reused by ``node_check`` for deterministic evaluation
    (e.g. the ``expected_value`` extracted from the developer intent).
    """
    if state.input is None:
        state.error = "No verified input available for planning."
        state.step = "complete"
        return state

    # Use the intent parser to extract structured requirements from
    # the developer intent.  This replaces the earlier coarse-grained
    # heuristic with a proper parsing pipeline.
    developer_intent = getattr(state.input, "developer_intent", None) or ""
    from backend.verification.intent.intent_parser import parse_intent
    parsed = parse_intent(developer_intent)

    if parsed["unsupported"]:
        state.error = (
            f"No verifiable requirements extracted from developer intent. "
            f"{parsed['ambiguity_reason']}"
        )
        state.step = "complete"
        return state

    # Extract VerificationRequirement objects from the parsed intent.
    from backend.verification.intent.requirement_extractor import extract_requirements
    from backend.verification.models import VerificationRequirement, RequirementType

    requirements = extract_requirements(parsed)
    if not requirements:
        state.error = (
            "No verifiable requirements extracted from developer intent. "
            "Add intent keywords such as 'reward', 'terminate', 'event', "
            "or 'metric'."
        )
        state.step = "complete"
        return state

    state.requirements = requirements

    # Produce dispatch plan from the requirements via the planner.
    try:
        from backend.verification.agent.workflow_planner import plan as plan_checks
        plan_result = plan_checks(requirements, state.context)
    except Exception as exc:
        state.error = f"Planning failed: {exc}"
        state.step = "complete"
        return state

    # Store the plan as a dict mapping req_id -> check_tool_id.
    # Consumers (node_check) expect an iterable of (req_id, check_tool_id) pairs.
    if isinstance(plan_result, dict):
        state.registered_checks = plan_result
    else:
        state.registered_checks = {}

    state.step = "checking"
    return state


def node_check(state: VerificationState) -> VerificationState:
    """Execute registered deterministic checks and collect results.

    For each registered check ID, build a minimal ``VerificationRequirement``
    and invoke the checker through the tool registry.  Individual check
    errors are recorded but do not prevent other checks from running.

    Key fix: extract evidence values (e.g. ``configured_reward``/``observed_reward``
    from the context's ``execution_evidence``) and pass them to the checker
    so that deterministic comparisons can be made with the requirement's
    expected values.
    """
    if state.input is None or state.context is None:
        state.error = "Missing input or context for check execution."
        state.step = "complete"
        return state

    state.check_results = {}

    # Helper: pull reward evidence from context if available
    def _reward_evidence(ctx) -> tuple:
        """Return (configured_reward, observed_reward) from execution_evidence."""
        try:
            # execution_evidence is nested inside the VerificationInput
            ev = getattr(ctx, "input", None)
            if ev is None:
                ev = ctx
            if ev and hasattr(ev, "execution_evidence"):
                ev = ev.execution_evidence
            if ev and isinstance(ev, dict):
                r = ev.get("reward")
                if isinstance(r, dict):
                    return float(r.get("expected") or 0), float(r.get("observed") or 0)
                if isinstance(r, (int, float)):
                    return float(r), float(r)
            return None, None
        except Exception:
            return None, None

    # Helper: pull metric observations from context if available
    def _metric_observations(ctx) -> list:
        try:
            ev = getattr(ctx, "input", None)
            if ev is None:
                ev = ctx
            if ev and hasattr(ev, "execution_evidence"):
                ev = ev.execution_evidence
            if ev and isinstance(ev, dict):
                return ev.get("metrics", ev.get("observations", []))
            return []
        except Exception:
            return []

    # Dispatch each registered check.
    for idx, (req_id, check_tool_id) in enumerate(state.registered_checks.items()):
        # Use the corresponding requirement from state.requirements, if available.
        # The planner processes requirements in order; we match by positional index.
        reqs = getattr(state, "requirements", []) or []
        if idx < len(reqs):
            req = reqs[idx]
        else:
            # Fallback: create a minimal requirement.
            req = VerificationRequirement(
                description=f"check:{check_tool_id}",
                type=RequirementType.reward,
                expected_value=None,
            )

        # Determine the requirement type from the check tool ID mapping.
        _TYPE_MAP: Dict[str, RequirementType] = {
            "check_reward": RequirementType.reward,
            "check_episode": RequirementType.termination,
            "check_metric": RequirementType.metric,
            "check_config": RequirementType.configuration,
        }
        check_type = _TYPE_MAP.get(check_tool_id, RequirementType.reward)

        # Extract evidence values from context for relevant check types
        reward_ev = _reward_evidence(state.context) if check_type == RequirementType.reward else (None, None)
        metric_obs = _metric_observations(state.context) if check_type == RequirementType.metric else None

        # Prepare checker arguments, injecting the requirement's expected value
        # and the context's evidence values.
        checker_args: Dict[str, Any] = {"requirement": req}

        if check_type == RequirementType.reward and reward_ev[0] is not None and reward_ev[1] is not None:
            # Use context evidence if available; otherwise fall back to requirement expected_value
            if req.expected_value is not None:
                checker_args["configured_reward"] = req.expected_value
            checker_args["observed_reward"] = reward_ev[1] if reward_ev[1] is not None else (req.expected_value or 0)
        elif check_type == RequirementType.metric and metric_obs is not None:
            checker_args["metric_observations"] = metric_obs

        try:
            # Execute the check through the registry.  The registry adapts
            # arguments to the handler's expected signature.
            result = execute_check(
                check_tool_id,
                state.context,
                checker_args,
            )
            state.check_results[req_id] = result
        except Exception as exc:
            logger.error(f"Check {check_tool_id} failed: {exc}")
            state.check_results[req_id] = VerificationCheckResult(
                requirement_id=req_id,
                status=CheckStatus.ERROR,
                expected=None,
                actual=None,
                tolerance=None,
                evidence_refs=[],
                details={"note": f"Check execution error: {exc}"},
            )

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

    # Phase 1 deterministic foundation does not automatically invoke Meta AI
    # for inconclusive cases; that decision point is handled by a higher layer.

    state.step = "complete"
    return state


def node_complete(state: VerificationState) -> VerificationState:
    """Final node — output the structured verification result.

    Builds the final output dict from the aggregated state.  Every terminal
    path produces a typed, serializable result.
    """
    # Build the final output dict
    output: Dict[str, Any] = {
        "overall_status": state.overall_status,
        "details": state.decision_details,
        "requirements": {},
    }

    # Attach per-requirement results
    if state.check_results:
        output["requirements"] = {
            rid: {
                "status": cr.status,
                "expected": getattr(cr, "expected", None),
                "actual": getattr(cr, "actual", None),
                "details": getattr(cr, "details", {}),
            }
            for rid, cr in state.check_results.items()
        }

    # Attach context-derived identifiers if available
    if state.context is not None:
        output["run_identifier"] = state.context.run_identifier
        output["environment_identifier"] = state.context.environment_identifier
        output["environment_version"] = state.context.environment_version

    # Attach the input agent ID if available
    if state.input is not None and hasattr(state.input, "agent_metadata"):
        output["agent_id"] = (
            getattr(state.input.agent_metadata, "agent_id", None) or None
        )

    # Store output on the state for the driver to retrieve
    state.output = output
    state.step = "complete"
    return state


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph() -> Any:
    """Build and return the LangGraph StateGraph for verification.

    The graph follows a linear progression: normalize → plan → check → aggregate → complete.
    No checkpointer is required for the basic workflow; callers use ``run_verification``
    which invokes ``app.invoke()`` without persistence semantics.
    """
    workflow = StateGraph(VerificationState)

    # Add nodes
    workflow.add_node("normalize", node_normalize)
    workflow.add_node("plan", node_plan)
    workflow.add_node("check", node_check)
    workflow.add_node("aggregate", node_aggregate)
    workflow.add_node("complete", node_complete)

    # Define edges (linear progression)
    workflow.set_entry_point("normalize")

    workflow.add_edge("normalize", "plan")
    workflow.add_edge("plan", "check")
    workflow.add_edge("check", "aggregate")
    workflow.add_edge("aggregate", "complete")
    workflow.add_edge("complete", END)

    # Compile without a checkpointer since the MVP uses invoke() without persistence.
    # A MemorySaver would require explicit 'configurable' keys at invoke time.
    app = workflow.compile()

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

    # Initial state — store raw_input so nodes can access it via state.raw_input
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

    # The result_state is a dict-like object returned by LangGraph's invoke.
    # Access fields via .get() rather than getattr() since the returned object
    # is an AccessibleValuesDict, not a VerificationState instance.
    overall = result_state.get("overall_status", "unknown")
    check_results = result_state.get("check_results") or {}
    details = result_state.get("decision_details", "No results obtained")

    # Build the output dict
    output: Dict[str, Any] = {
        "overall_status": overall,
        "details": details,
        "requirements": {},
    }

    # Attach per-requirement results if available
    if check_results:
        output["requirements"] = {
            rid: {
                "status": cr.status,
                "expected": getattr(cr, "expected", None),
                "actual": getattr(cr, "actual", None),
                "details": getattr(cr, "details", {}),
            }
            for rid, cr in check_results.items()
        }

    # Attach context-derived identifiers if available
    context = result_state.get("context")
    if context is not None:
        output["run_identifier"] = getattr(context, "run_identifier", None)
        output["environment_identifier"] = getattr(context, "environment_identifier", None)
        output["environment_version"] = getattr(context, "environment_version", None)

    # Attach the input agent ID if available
    input_data = result_state.get("input")
    if input_data is not None and hasattr(input_data, "agent_metadata"):
        agent_meta = input_data.agent_metadata
        output["agent_id"] = getattr(agent_meta, "agent_id", None)

    # Attach the workflow step and any error information
    output["step"] = result_state.get("step", "unknown")
    if result_state.get("error"):
        output["error"] = result_state["error"]

    return output


# Helper: map check tool IDs to requirement types
def _requirement_type_from_id(check_tool_id: str) -> Any:
    """Return a RequirementType for a given check tool identifier.

    The mapping is intentionally simple for the MVP; each checker knows how
    to handle its own requirement type, so we default to ``RequirementType.reward``
    when the ID is unrecognised.
    """
    _MAP: Dict[str, Any] = {
        "check_reward": RequirementType.reward,
        "check_episode": RequirementType.termination,
        "check_event": RequirementType.event,
        "check_metric": RequirementType.metric,
        "check_config": RequirementType.configuration,
    }
    return _MAP.get(check_tool_id, RequirementType.reward)