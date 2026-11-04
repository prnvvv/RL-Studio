"""LangGraph orchestration for the Phase 3 verification lifecycle.

Two compiled graphs share one service (the nodes are thin; business rules live in ``service.py``):

``intake``     input -> run/evidence retrieval -> replay check -> intent read (AI) -> requirement
               extraction (AI) -> deterministic validation -> persistence
``execution``  confirmed requirements -> evidence retrieval -> scope check -> idempotency ->
               deterministic verification -> persistence -> incident handoff

User confirmation is a real pause between the two graphs: it is an API call (``confirm``/``reject``),
never something a model can do. Only the two AI nodes (``interpret``, ``extract``) touch a model;
retrieval, validation, verification, persistence and the incident handoff are normal services.

Every state carries a ``trail`` of visited nodes so a run of the workflow can be inspected.
"""

from __future__ import annotations

import operator
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from backend.ai.errors import AIError
from backend.ai.registry import Task
from backend.database.utils import utc_now_iso
from backend.verification.intent.ai_interpreter import (
    PROVIDER_UNAVAILABLE,
    REJECTED_INPUT,
    SETTLED_STATUSES,
    IntentInterpreter,
    InterpretationResult,
)
from backend.verification.lifecycle import service as svc_mod

if TYPE_CHECKING:  # pragma: no cover - typing only
    from backend.verification.lifecycle.service import VerificationLifecycle


class IntakeState(TypedDict, total=False):
    run_id: str
    statement: str
    context: dict[str, Any]
    idempotency_key: str
    trail: Annotated[list[str], operator.add]
    prepared: Any
    catalogue: dict[str, Any]
    reading: Any
    stages: list[dict[str, Any]]
    result: InterpretationResult
    records: list[dict[str, Any]]
    intent_id: str
    outcome: str
    reason: str


class ExecutionState(TypedDict, total=False):
    run_id: str
    requirement_ids: list[str] | None
    idempotency_key: str | None
    trail: Annotated[list[str], operator.add]
    records: list[dict[str, Any]]
    prepared: Any
    key: str
    verification_id: str
    output: dict[str, Any]
    outcome: str
    reason: str
    details: dict[str, Any]
    overall_status: str


@dataclass
class Graphs:
    intake: Any
    execution: Any


def build_graphs(svc: VerificationLifecycle) -> Graphs:
    return Graphs(_intake_graph(svc), _execution_graph(svc))


# ====================================================================================================
def _intake_graph(svc: VerificationLifecycle) -> Any:
    def validate_input(s: IntakeState) -> IntakeState:
        reason = IntentInterpreter.check_input(s["statement"])
        if reason:
            return {"trail": ["validate_input"], "outcome": REJECTED_INPUT, "reason": reason}
        return {"trail": ["validate_input"]}

    def retrieve_evidence(s: IntakeState) -> IntakeState:
        try:
            prepared = svc.prepare_evidence(s["run_id"])
        except svc_mod.RunNotFound:
            return {"trail": ["retrieve_evidence"], "outcome": "run_not_found"}
        return {"trail": ["retrieve_evidence"], "prepared": prepared, "catalogue": prepared.facts.describe()}

    def replay_check(s: IntakeState) -> IntakeState:
        found = svc.store.find_intent_by_key(s["idempotency_key"], s["run_id"], SETTLED_STATUSES)
        if found is not None:
            return {"trail": ["replay_check"], "outcome": "replayed", "intent_id": found["intent_id"]}
        return {"trail": ["replay_check"]}

    def interpret(s: IntakeState) -> IntakeState:
        text = s["statement"].strip()
        if svc.interpreter is None:
            return {"trail": ["interpret"], "result": InterpretationResult(
                PROVIDER_UNAVAILABLE, "no hosted AI service is configured", ai={"error": {"code": "AI-001", "category": "AIConfigurationError", "message": "no hosted AI service is configured"}}),
                "stages": []}
        try:
            reading, meta = svc.interpreter.read(text, s["catalogue"], s.get("context"))
        except AIError as exc:
            res = svc.interpreter.failed(text, exc, [svc.interpreter.error_stage(Task.INTENT, exc)])
            return {"trail": ["interpret"], "result": res}
        return {"trail": ["interpret"], "reading": reading, "stages": [meta]}

    def extract(s: IntakeState) -> IntakeState:
        text = s["statement"].strip()
        try:
            reqset, meta = svc.interpreter.propose(text, s["reading"], s["catalogue"])  # type: ignore[union-attr]
        except AIError as exc:
            res = svc.interpreter.failed(  # type: ignore[union-attr]
                text, exc, [*s["stages"], svc.interpreter.error_stage(Task.REQUIREMENTS, exc)], s["reading"])
            return {"trail": ["extract"], "result": res}
        res = svc.interpreter.success(s["reading"], reqset, [*s["stages"], meta])  # type: ignore[union-attr]
        return {"trail": ["extract"], "result": res}

    def validate_requirements(s: IntakeState) -> IntakeState:
        prepared = s["prepared"]
        intent_id = s.get("intent_id") or str(uuid.uuid4())
        records = svc.materialize(intent_id, s["run_id"], s["statement"], s.get("context") or {}, s["result"], prepared.facts)
        return {"trail": ["validate_requirements"], "records": records, "intent_id": intent_id}

    def persist(s: IntakeState) -> IntakeState:
        res: InterpretationResult = s["result"]
        prepared = s["prepared"]
        intent_id = s.get("intent_id") or str(uuid.uuid4())
        records = s.get("records") or []
        status = res.status  # a provider failure is recorded as such; nothing is fabricated
        ai = {**res.ai, "origin": res.origin}
        stated = (s.get("context") or {}).get("environment_version")
        svc.store.save_intent({
            "intent_id": intent_id, "run_id": s["run_id"], "environment_id": prepared.facts.environment_id,
            "environment_version": stated or prepared.facts.environment_version,
            "original_text": s["statement"].strip(), "context": s.get("context") or {}, "status": status,
            "status_reason": res.reason, "interpretation": {**res.interpretation, "reported_contradictions": res.reported_contradictions},
            "ai": ai, "idempotency_key": s["idempotency_key"],
            "source_refs": {
                "run_id": s["run_id"], "evidence_fingerprint": prepared.fingerprint,
                "run_environment_version": prepared.facts.environment_version,
                "episodes": prepared.facts.episode_count, "events": prepared.facts.event_count,
                "missing_evidence": list(prepared.facts.missing_evidence), "retrieved_at": utc_now_iso(),
            },
        })
        for rec in records:
            svc.store.save_requirement(rec)
        return {"trail": ["persist"], "intent_id": intent_id, "outcome": "stored"}

    # -- routing ------------------------------------------------------------------------------------
    def after_validate(s: IntakeState) -> str:
        return "end" if s.get("outcome") == REJECTED_INPUT else "retrieve_evidence"

    def after_retrieve(s: IntakeState) -> str:
        return "end" if s.get("outcome") == "run_not_found" else "replay_check"

    def after_replay(s: IntakeState) -> str:
        return "end" if s.get("outcome") == "replayed" else "interpret"

    def after_interpret(s: IntakeState) -> str:
        res = s.get("result")
        if res is None:
            return "extract"
        return "validate_requirements" if res.proposals else "persist"  # failure / deterministic fallback

    def after_extract(s: IntakeState) -> str:
        res: InterpretationResult = s["result"]
        return "validate_requirements" if res.proposals else "persist"

    g = StateGraph(IntakeState)
    for name, fn in (("validate_input", validate_input), ("retrieve_evidence", retrieve_evidence),
                     ("replay_check", replay_check), ("interpret", interpret), ("extract", extract),
                     ("validate_requirements", validate_requirements), ("persist", persist)):
        g.add_node(name, fn)
    g.set_entry_point("validate_input")
    g.add_conditional_edges("validate_input", after_validate, {"end": END, "retrieve_evidence": "retrieve_evidence"})
    g.add_conditional_edges("retrieve_evidence", after_retrieve, {"end": END, "replay_check": "replay_check"})
    g.add_conditional_edges("replay_check", after_replay, {"end": END, "interpret": "interpret"})
    g.add_conditional_edges("interpret", after_interpret, {"extract": "extract", "validate_requirements": "validate_requirements", "persist": "persist"})
    g.add_conditional_edges("extract", after_extract, {"validate_requirements": "validate_requirements", "persist": "persist"})
    g.add_edge("validate_requirements", "persist")
    g.add_edge("persist", END)
    return g.compile()


# ====================================================================================================
def _execution_graph(svc: VerificationLifecycle) -> Any:
    def load_requirements(s: ExecutionState) -> ExecutionState:
        if svc.reader.get_run(s["run_id"]) is None:
            return {"trail": ["load_requirements"], "outcome": "run_not_found"}
        records, reason, details = svc.select_requirements(s["run_id"], s.get("requirement_ids"))
        if reason == "no_confirmed_requirements":
            return {"trail": ["load_requirements"], "outcome": "no_confirmed_requirements"}
        if reason:
            return {"trail": ["load_requirements"], "outcome": "invalid_selection", "reason": reason, "details": details}
        if len(records) > svc_mod.MAX_REQUIREMENTS_PER_EXECUTION:
            return {"trail": ["load_requirements"], "outcome": "invalid_selection",
                    "reason": f"at most {svc_mod.MAX_REQUIREMENTS_PER_EXECUTION} requirements per verification", "details": {}}
        return {"trail": ["load_requirements"], "records": records}

    def retrieve_evidence(s: ExecutionState) -> ExecutionState:
        try:
            prepared = svc.prepare_evidence(s["run_id"])
        except svc_mod.RunNotFound:
            return {"trail": ["retrieve_evidence"], "outcome": "run_not_found"}
        return {"trail": ["retrieve_evidence"], "prepared": prepared}

    def idempotency(s: ExecutionState) -> ExecutionState:
        prepared = s["prepared"]
        key = s.get("idempotency_key") or svc_mod._sha(
            s["run_id"], sorted((r["requirement_id"], r["requirement"]) for r in s["records"]), prepared.fingerprint)
        existing = svc.store.find_verification_by_key(key)
        if existing is not None:
            return {"trail": ["idempotency"], "key": key, "outcome": "replayed", "verification_id": existing["verification_id"]}
        return {"trail": ["idempotency"], "key": key, "verification_id": str(uuid.uuid4())}

    def verify(s: ExecutionState) -> ExecutionState:
        output, _blocked = svc.run_engine(s["run_id"], s["records"], s["prepared"], s["verification_id"])
        return {"trail": ["verify"], "output": output, "overall_status": output.get("overall_status", "unknown")}

    def persist(s: ExecutionState) -> ExecutionState:
        saved = svc.persist_verification(s["run_id"], s["records"], s["prepared"], s["output"], s["verification_id"], s["key"])
        return {"trail": ["persist"], "verification_id": saved["verification_id"], "outcome": "stored"}

    def handoff(s: ExecutionState) -> ExecutionState:
        svc.handoff(s["verification_id"])
        return {"trail": ["incident_handoff"]}

    def no_incident(s: ExecutionState) -> ExecutionState:
        svc.handoff(s["verification_id"])  # records 'not_required' (policy decides, not this graph)
        return {"trail": ["no_incident"]}

    def after_load(s: ExecutionState) -> str:
        return "end" if s.get("outcome") else "retrieve_evidence"

    def after_retrieve(s: ExecutionState) -> str:
        return "end" if s.get("outcome") == "run_not_found" else "idempotency"

    def after_idempotency(s: ExecutionState) -> str:
        return "incident_handoff" if s.get("outcome") == "replayed" else "verify"

    def after_persist(s: ExecutionState) -> str:
        return "incident_handoff" if s.get("overall_status") in ("fail", "error") else "no_incident"

    g = StateGraph(ExecutionState)
    for name, fn in (("load_requirements", load_requirements), ("retrieve_evidence", retrieve_evidence),
                     ("idempotency", idempotency), ("verify", verify), ("persist", persist),
                     ("incident_handoff", handoff), ("no_incident", no_incident)):
        g.add_node(name, fn)
    g.set_entry_point("load_requirements")
    g.add_conditional_edges("load_requirements", after_load, {"end": END, "retrieve_evidence": "retrieve_evidence"})
    g.add_conditional_edges("retrieve_evidence", after_retrieve, {"end": END, "idempotency": "idempotency"})
    g.add_conditional_edges("idempotency", after_idempotency, {"incident_handoff": "incident_handoff", "verify": "verify"})
    g.add_edge("verify", "persist")
    g.add_conditional_edges("persist", after_persist, {"incident_handoff": "incident_handoff", "no_incident": "no_incident"})
    g.add_edge("incident_handoff", END)
    g.add_edge("no_incident", END)
    return g.compile()


__all__ = ["Graphs", "build_graphs"]
