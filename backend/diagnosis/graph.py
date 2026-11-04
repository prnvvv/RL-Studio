"""LangGraph workflow for incident investigation and recovery planning.

``load_context -> reuse_check -> gate -> reason (Muse Wonder) -> ground -> persist``

Only ``reason`` touches a model. Context retrieval, the reuse check, the evidence gate, grounding and persistence are
ordinary code: a model is called once per distinct evidence context (never per training step), and not at all when
the persisted evidence is insufficient or an identical analysis already exists. The model never decides a
verification verdict and never executes anything; its output is checked against the persisted evidence by
``grounding.py`` before it is stored.

Every state carries a ``trail`` of visited nodes so a run of the workflow can be inspected, mirroring the Phase 3
verification graphs.
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from backend.ai.errors import AIError
from backend.ai.registry import Task

from .grounding import ground_recovery, ground_root_cause
from .models import KIND_RECOVERY_PLAN, KIND_ROOT_CAUSE, RecoveryPlan, RootCauseAnalysis
from .prompts import (
    PROMPT_VERSION_RECOVERY,
    PROMPT_VERSION_ROOT_CAUSE,
    recovery_messages,
    root_cause_messages,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .service import DiagnosisService

STATUS_COMPLETED = "completed"
STATUS_INSUFFICIENT = "insufficient_evidence"


class DiagnosisState(TypedDict, total=False):
    incident_id: str
    kind: str
    force: bool
    trail: Annotated[list[str], operator.add]
    ctx: Any
    prior: dict[str, Any] | None
    outcome: str
    ai_result: Any
    analysis: Any
    grounded: dict[str, Any]
    error: Exception
    record: dict[str, Any]


def build_diagnosis_graph(svc: DiagnosisService) -> Any:
    def load_context(s: DiagnosisState) -> DiagnosisState:
        prior = svc.store.latest(s["incident_id"], KIND_ROOT_CAUSE) if s["kind"] == KIND_RECOVERY_PLAN else None
        ctx = svc.builder.build(s["incident_id"], prior=prior)
        return {"trail": ["load_context"], "ctx": ctx, "prior": prior}

    def reuse_check(s: DiagnosisState) -> DiagnosisState:
        if not s.get("force"):
            found = svc.store.latest(s["incident_id"], s["kind"], context_hash=s["ctx"].context_hash)
            if found is not None:
                return {"trail": ["reuse_check"], "outcome": "reused", "record": found}
        return {"trail": ["reuse_check"]}

    def gate(s: DiagnosisState) -> DiagnosisState:
        if not s["ctx"].sufficient:
            return {"trail": ["gate"], "outcome": STATUS_INSUFFICIENT}
        return {"trail": ["gate"]}

    def reason(s: DiagnosisState) -> DiagnosisState:
        ctx = s["ctx"]
        if s["kind"] == KIND_ROOT_CAUSE:
            task, messages, schema = Task.ROOT_CAUSE, root_cause_messages(ctx.payload), RootCauseAnalysis
        else:
            task, messages, schema = Task.RECOVERY_PLANNING, recovery_messages(ctx.payload), RecoveryPlan
        try:
            res = svc.ai.run_text(task, messages, schema)
        except AIError as exc:
            return {"trail": ["reason"], "outcome": "ai_failed", "error": exc}
        return {"trail": ["reason"], "ai_result": res, "analysis": res.parsed}

    def ground(s: DiagnosisState) -> DiagnosisState:
        ground_fn = ground_root_cause if s["kind"] == KIND_ROOT_CAUSE else ground_recovery
        return {"trail": ["ground"], "grounded": ground_fn(s["analysis"], s["ctx"])}

    def persist(s: DiagnosisState) -> DiagnosisState:
        ctx = s["ctx"]
        warnings: list[str] = []
        if s.get("outcome") == STATUS_INSUFFICIENT:
            result = {"summary": "", "missing_evidence": ctx.missing_evidence,
                      "message": "The persisted evidence is insufficient for an investigation; no model was called."}
            ai: dict[str, Any] = {"called": False}
            status = STATUS_INSUFFICIENT
        else:
            res = s["ai_result"]
            result = s["grounded"]
            status = STATUS_COMPLETED
            ai = {"called": True, "task": res.task, "provider": res.provider, "model": res.model,
                  "fallback_used": res.fallback_used, "request_id": res.request_id, "usage": res.usage,
                  "prompt_version": PROMPT_VERSION_ROOT_CAUSE if s["kind"] == KIND_ROOT_CAUSE else PROMPT_VERSION_RECOVERY}
            if res.fallback_used:
                warnings.append(f"the preferred reasoning model was unavailable; {res.model} was used instead")
            if result.get("ungrounded_references"):
                warnings.append(f"{len(result['ungrounded_references'])} model citation(s) did not match persisted "
                                "evidence and were removed")
        record = svc.store.save(
            incident_id=s["incident_id"], run_id=ctx.run_id, kind=s["kind"], status=status,
            context_hash=ctx.context_hash, evidence_index=ctx.evidence_index, result=result, ai=ai,
            warnings=warnings, based_on=ctx.prior_investigation_id)
        return {"trail": ["persist"], "record": record, "outcome": status}

    def after_reuse(s: DiagnosisState) -> str:
        return END if s.get("outcome") == "reused" else "gate"

    def after_gate(s: DiagnosisState) -> str:
        return "persist" if s.get("outcome") == STATUS_INSUFFICIENT else "reason"

    def after_reason(s: DiagnosisState) -> str:
        return END if s.get("outcome") == "ai_failed" else "ground"

    graph = StateGraph(DiagnosisState)
    for name, fn in (("load_context", load_context), ("reuse_check", reuse_check), ("gate", gate),
                     ("reason", reason), ("ground", ground), ("persist", persist)):
        graph.add_node(name, fn)
    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "reuse_check")
    graph.add_conditional_edges("reuse_check", after_reuse, {END: END, "gate": "gate"})
    graph.add_conditional_edges("gate", after_gate, {"persist": "persist", "reason": "reason"})
    graph.add_conditional_edges("reason", after_reason, {END: END, "ground": "ground"})
    graph.add_edge("ground", "persist")
    graph.add_edge("persist", END)
    return graph.compile()
