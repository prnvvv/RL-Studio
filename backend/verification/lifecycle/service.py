"""Phase 3 service: intent -> requirements -> confirmation -> deterministic verification -> incident.

Division of authority
    hosted AI        proposes requirements (advisory, schema-validated)
    this service     validates them deterministically, persists every step, hands failures to Person 4
    the engine       (``run_verification_state``) alone decides PASS/FAIL/UNKNOWN per requirement and overall
    Person 4         owns the incident record (``ProvenanceService.register_incident``)

The LangGraph orchestration lives in ``graphs.py``; the nodes call the methods defined here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from backend.ai.service import AIService
from backend.database.connection import Database
from backend.provenance.service import ProvenanceService
from backend.studio.store import TrajectoryReader
from backend.verification.agent.verification_agent import run_verification_state
from backend.verification.incidents.sink import (
    IncidentSink,
    ProvenanceIncidentSink,
    build_incident_draft,
)
from backend.verification.input.studio_evidence import (
    StudioEvidence,
    StudioRunNotFoundError,
    build_studio_evidence,
)
from backend.verification.intent import requirement_validation as rv
from backend.verification.intent.ai_interpreter import (
    IntentInterpreter,
    InterpretationResult,
    ProposedRequirement,
)
from backend.verification.models import (
    RequirementSource,
    RequirementType,
    VerificationRequirement,
)
from backend.verification.storage.sqlite_store import SqliteVerificationStore

logger = logging.getLogger(__name__)

MAX_REQUIREMENTS_PER_EXECUTION = 50
OVERRIDABLE = ("expected_value", "comparison_operator", "tolerance", "metric_name", "config_key",
               "max_steps", "required_event", "forbidden_event")
_ENGINE_FIELDS = ("expected_value", "comparison_operator", "tolerance")
_NS = uuid.NAMESPACE_URL


# ---- errors (mapped to HTTP by the router) -------------------------------------------------------
class LifecycleError(Exception):
    code = "verification_error"
    http_status = 400

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidRequest(LifecycleError):
    code, http_status = "invalid_request", 422


class RunNotFound(LifecycleError):
    code, http_status = "run_not_found", 404


class NotFound(LifecycleError):
    code, http_status = "not_found", 404


class Conflict(LifecycleError):
    code, http_status = "conflict", 409


# ---- helpers -------------------------------------------------------------------------------------
def _sha(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, sort_keys=True, separators=(",", ":"), default=str).encode())
        h.update(b"\x1f")
    return h.hexdigest()


def evidence_fingerprint(payload: dict[str, Any]) -> str:
    return _sha(payload.get("execution_evidence"), payload.get("environment_config"), payload.get("training_config"))


def incident_id_for(verification_id: str) -> str:
    return str(uuid.uuid5(_NS, f"rl-studio:incident:{verification_id}"))


@dataclass
class PreparedEvidence:
    evidence: StudioEvidence
    facts: rv.EvidenceFacts
    fingerprint: str


class VerificationLifecycle:
    def __init__(
        self,
        *,
        database: Database,
        reader: TrajectoryReader,
        provenance: ProvenanceService,
        ai: AIService | None = None,
        incident_sink: IncidentSink | None = None,
        allow_fallback: bool = True,
    ) -> None:
        self.database = database
        self.reader = reader
        self.provenance = provenance
        self.store = SqliteVerificationStore(database)
        self.ai = ai
        self.interpreter = IntentInterpreter(ai, allow_fallback=allow_fallback) if ai is not None else None
        self.sink: IncidentSink = incident_sink or ProvenanceIncidentSink(provenance)
        self._graphs: Any = None

    # ---- evidence ---------------------------------------------------------------------------
    def prepare_evidence(self, run_id: str) -> PreparedEvidence:
        """Persisted Phase 2 evidence for the run. Raises ``RunNotFound``."""
        try:
            evidence = build_studio_evidence(run_id, reader=self.reader, provenance=self.provenance)
        except StudioRunNotFoundError as exc:
            raise RunNotFound("the run does not exist", {"run_id": run_id}) from exc
        # Same recorded configuration, addressable by dotted key (agent_params.learning_rate, ...).
        evidence.payload["environment_config"] = rv.flatten_config(evidence.payload)
        facts = rv.EvidenceFacts.from_payload(evidence.payload, evidence.missing_evidence)
        return PreparedEvidence(evidence, facts, evidence_fingerprint(evidence.payload))

    # ---- graphs ------------------------------------------------------------------------------
    @property
    def graphs(self) -> Any:
        if self._graphs is None:
            from backend.verification.lifecycle.graphs import build_graphs

            self._graphs = build_graphs(self)
        return self._graphs

    # ---- intents ------------------------------------------------------------------------------
    def submit_intent(
        self, run_id: str, statement: str, context: dict[str, Any] | None = None, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        key = idempotency_key or _sha(run_id, rv.normalize_ws(statement), context or {})
        state = self.graphs.intake.invoke({
            "run_id": run_id, "statement": statement, "context": context or {}, "idempotency_key": key, "trail": [],
        })
        outcome = state.get("outcome")
        if outcome == "rejected_input":
            raise InvalidRequest(state.get("reason") or "invalid statement", {"run_id": run_id})
        if outcome == "run_not_found":
            raise RunNotFound("the run does not exist", {"run_id": run_id})
        view = self.get_intent(state["intent_id"])
        view["replayed"] = outcome == "replayed"
        view["workflow"] = {"path": state.get("trail", [])}
        return view

    def get_intent(self, intent_id: str) -> dict[str, Any]:
        rec = self.store.get_intent(intent_id)
        if rec is None:
            raise NotFound("intent not found", {"intent_id": intent_id})
        reqs = [self.requirement_view(r) for r in self.store.list_requirements(intent_id=intent_id)]
        return {**self.intent_view(rec), "requirements": reqs}

    def list_intents(self, run_id: str) -> list[dict[str, Any]]:
        self._require_run(run_id)
        return [self.get_intent(r["intent_id"]) for r in self.store.list_intents(run_id)]

    def _require_run(self, run_id: str) -> None:
        if self.reader.get_run(run_id) is None:
            raise RunNotFound("the run does not exist", {"run_id": run_id})

    @staticmethod
    def intent_view(rec: dict[str, Any]) -> dict[str, Any]:
        ai = rec.get("ai") or {}
        stages = ai.get("stages") or []
        return {
            "intent_id": rec["intent_id"], "run_id": rec["run_id"], "environment_id": rec.get("environment_id"),
            "environment_version": rec.get("environment_version"), "original_text": rec["original_text"],
            "status": rec["status"], "status_reason": rec.get("status_reason"),
            "interpretation": rec.get("interpretation") or {},
            "ai": {
                "stages": [{k: v for k, v in s.items() if k != "usage"} | ({"usage": s["usage"]} if s.get("usage") else {})
                           for s in stages],
                "prompt_version": ai.get("prompt_version"), "error": ai.get("error"),
                "origin": ai.get("origin"),
            },
            "source_refs": rec.get("source_refs") or {}, "created_at": rec["created_at"],
            "updated_at": rec["updated_at"],
        }

    # ---- proposals -> requirement records ---------------------------------------------------------
    def materialize(
        self, intent_id: str, run_id: str, statement: str, context: dict[str, Any], result: InterpretationResult,
        facts: rv.EvidenceFacts,
    ) -> list[dict[str, Any]]:
        stated_version = (context or {}).get("environment_version")
        version = stated_version or facts.environment_version
        records: list[dict[str, Any]] = []
        reqs: list[VerificationRequirement] = []
        proposals: list[ProposedRequirement] = list(result.proposals)
        for p in proposals:
            reqs.append(self._to_requirement(p, intent_id, run_id, facts, version, result.origin))
        outcomes = [
            rv.validate_proposal(r, facts, run_id=run_id, source_statement=p.source_statement, user_statement=statement)
            for r, p in zip(reqs, proposals, strict=True)
        ]
        # contradictions the deterministic logic can prove
        by_id = {r.id: i for i, r in enumerate(reqs)}
        live = [r for r, o in zip(reqs, outcomes, strict=True) if o.status != rv.V_INVALID]
        for ids, why in rv.find_contradictions(live):
            for rid in ids:
                o = outcomes[by_id[rid]]
                o.status = rv.V_INVALID
                o.reasons.append(f"contradictory requirements: {why}")
        # contradictions only the model reported: ask the user instead of deciding
        for c in result.reported_contradictions:
            texts = [result.interpretation.get("statements", [])[i]["text"] for i in c.get("statements", [])
                     if isinstance(i, int) and 0 <= i < len(result.interpretation.get("statements", []))]
            for p, o in zip(proposals, outcomes, strict=True):
                if o.status == rv.V_VALID and any(t and (t in p.source_statement or p.source_statement in t) for t in texts):
                    o.status = rv.V_CLARIFY
                    o.reasons.append(f"possible conflict between expectations (reported by the model): {c.get('reason', '')}")
        for r, p, o in zip(reqs, proposals, outcomes, strict=True):
            lifecycle = {
                rv.V_VALID: rv.NEEDS_CLARIFICATION if p.needs_clarification else rv.DRAFT,
                rv.V_NOT_EVALUABLE: rv.DRAFT, rv.V_CLARIFY: rv.NEEDS_CLARIFICATION, rv.V_INVALID: rv.INVALID,
            }[o.status]
            validation = o.to_dict()
            if lifecycle == rv.NEEDS_CLARIFICATION:
                validation["clarification_question"] = p.clarification_question or (o.reasons[0] if o.reasons else
                                                                                    "please state the missing detail")
            records.append(self._record(r, intent_id, run_id, facts, p.source_statement, lifecycle, o.status, validation))
        return records

    @staticmethod
    def _to_requirement(
        p: ProposedRequirement, intent_id: str, run_id: str, facts: rv.EvidenceFacts, version: str | None, origin: str
    ) -> VerificationRequirement:
        md: dict[str, Any] = {
            "origin": origin, "intent_id": intent_id, "run_id": run_id, "environment_id": facts.environment_id,
            "environment_version": version, "source_statement": p.source_statement, "criterion": p.criterion,
            "evidence_required": p.evidence_required or rv.EVIDENCE_REQUIRED.get(p.type, []),
        }
        for key in ("metric_name", "required_event", "forbidden_event", "config_key", "max_steps"):
            value = getattr(p, key)
            if value is not None:
                md[key] = value
        expected = p.max_steps if (p.type == "termination" and p.max_steps is not None) else p.expected_value
        return VerificationRequirement(
            description=p.description, source=RequirementSource.code_inferred, type=RequirementType(p.type),
            expected_value=expected, comparison_operator=p.comparison_operator, tolerance=p.tolerance,
            is_mandatory=True, metadata=md,
        )

    @staticmethod
    def _record(
        r: VerificationRequirement, intent_id: str, run_id: str, facts: rv.EvidenceFacts, source_statement: str,
        lifecycle: str, validation_status: str, validation: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "requirement_id": r.id, "intent_id": intent_id, "run_id": run_id, "environment_id": facts.environment_id,
            "environment_version": (r.metadata or {}).get("environment_version"), "category": r.type.value,
            "source_statement": source_statement, "description": r.description,
            "criterion": (r.metadata or {}).get("criterion"), "comparison_operator": r.comparison_operator,
            "expected_value": r.expected_value, "tolerance": r.tolerance,
            "evidence_required": (r.metadata or {}).get("evidence_required") or [],
            "lifecycle_status": lifecycle, "validation_status": validation_status, "validation": validation,
            "requirement": r.model_dump(mode="json"),
        }

    @staticmethod
    def requirement_view(rec: dict[str, Any]) -> dict[str, Any]:
        req = rec["requirement"]
        md = req.get("metadata") or {}
        confirmed = req.get("source") == RequirementSource.developer_confirmed.value
        validation = rec.get("validation") or {}
        return {
            "requirement_id": rec["requirement_id"], "intent_id": rec["intent_id"], "run_id": rec["run_id"],
            "environment_id": rec.get("environment_id"), "environment_version": rec.get("environment_version"),
            "category": rec["category"], "source_statement": rec["source_statement"],
            "description": rec["description"], "criterion": rec.get("criterion"),
            "comparison_operator": rec.get("comparison_operator"), "expected_value": rec.get("expected_value"),
            "tolerance": rec.get("tolerance"), "evidence_required": rec.get("evidence_required") or [],
            "target": {k: md[k] for k in ("metric_name", "config_key", "required_event", "forbidden_event", "max_steps") if k in md},
            "origin": md.get("origin"), "is_mandatory": req.get("is_mandatory", True),
            "lifecycle_status": rec["lifecycle_status"], "validation_status": rec["validation_status"],
            "validation": validation, "clarification_question": validation.get("clarification_question"),
            "confirmation_status": "rejected" if rec["lifecycle_status"] == rv.REJECTED else
                                   "confirmed" if confirmed else "proposed",
            "verification_id": rec.get("last_verification_id"), "last_result_status": rec.get("last_result_status"),
            "created_at": rec["created_at"], "confirmed_at": rec.get("confirmed_at"),
        }

    # ---- confirmation / rejection ------------------------------------------------------------------
    def confirm_requirement(self, requirement_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        rec = self.store.get_requirement(requirement_id)
        if rec is None:
            raise NotFound("requirement not found", {"requirement_id": requirement_id})
        state = rec["lifecycle_status"]
        confirmed = rec["requirement"].get("source") == RequirementSource.developer_confirmed.value
        if confirmed and not overrides:
            return self.requirement_view(rec)  # idempotent
        if state == rv.REJECTED:
            raise Conflict("a rejected requirement cannot be confirmed", {"requirement_id": requirement_id})
        if state == rv.INVALID:
            raise Conflict("an invalid requirement cannot be confirmed", {
                "requirement_id": requirement_id, "reasons": (rec.get("validation") or {}).get("reasons", [])})
        if confirmed:
            raise Conflict("a confirmed requirement is immutable; reject it and submit a new expectation",
                           {"requirement_id": requirement_id})

        req = VerificationRequirement.model_validate(rec["requirement"])
        md = dict(req.metadata or {})
        fields: dict[str, Any] = {k: getattr(req, k) for k in _ENGINE_FIELDS}
        applied: dict[str, Any] = {}
        for key, value in (overrides or {}).items():
            if key not in OVERRIDABLE:
                raise InvalidRequest(f"cannot override {key!r}", {"allowed": list(OVERRIDABLE)})
            applied[key] = value
            if key in _ENGINE_FIELDS:
                fields[key] = value
            else:
                md[key] = value
        if "max_steps" in applied:
            fields["expected_value"] = applied["max_steps"]
        prepared = self.prepare_evidence(rec["run_id"])
        intent = self.store.get_intent(rec["intent_id"]) or {}
        stated = rv.normalize_ws(f"{intent.get('original_text', '')} " + " ".join(f"{k} {v}" for k, v in applied.items()))
        candidate = req.model_copy(update={**fields, "metadata": md})
        outcome = rv.validate_proposal(
            candidate, prepared.facts, run_id=rec["run_id"], source_statement=rec["source_statement"], user_statement=stated)
        validation = outcome.to_dict()
        if applied:
            validation["user_supplied_overrides"] = applied
        if outcome.status in (rv.V_VALID, rv.V_NOT_EVALUABLE):
            md["confirmed_by"] = "developer"
            if applied:
                md["user_supplied_overrides"] = sorted(applied)
            final = candidate.model_copy(update={"source": RequirementSource.developer_confirmed, "metadata": md})
            self.store.update_requirement(
                requirement_id, lifecycle_status=rv.CONFIRMED, validation_status=outcome.status, validation=validation,
                requirement=final.model_dump(mode="json"), confirmed_at=_now(), expected_value=final.expected_value,
                comparison_operator=final.comparison_operator, tolerance=final.tolerance)
            return self.requirement_view(self.store.get_requirement(requirement_id))  # type: ignore[arg-type]
        lifecycle = rv.INVALID if outcome.status == rv.V_INVALID else rv.NEEDS_CLARIFICATION
        if lifecycle == rv.NEEDS_CLARIFICATION:
            validation["clarification_question"] = outcome.reasons[0] if outcome.reasons else "please state the missing detail"
        self.store.update_requirement(requirement_id, lifecycle_status=lifecycle, validation_status=outcome.status, validation=validation)
        raise Conflict("the requirement cannot be confirmed yet", {
            "requirement_id": requirement_id, "validation_status": outcome.status, "reasons": outcome.reasons})

    def reject_requirement(self, requirement_id: str, reason: str | None = None) -> dict[str, Any]:
        rec = self.store.get_requirement(requirement_id)
        if rec is None:
            raise NotFound("requirement not found", {"requirement_id": requirement_id})
        if rec["lifecycle_status"] in (rv.VERIFIED, rv.FAILED, rv.UNKNOWN) or \
                rec["requirement"].get("source") == RequirementSource.developer_confirmed.value:
            raise Conflict("a confirmed requirement cannot be rejected; its verification history is preserved",
                           {"requirement_id": requirement_id})
        validation = {**(rec.get("validation") or {}), "rejection_reason": (reason or "")[:500] or None}
        self.store.update_requirement(requirement_id, lifecycle_status=rv.REJECTED, validation=validation)
        return self.requirement_view(self.store.get_requirement(requirement_id))  # type: ignore[arg-type]

    def list_requirements(self, run_id: str) -> list[dict[str, Any]]:
        self._require_run(run_id)
        return [self.requirement_view(r) for r in self.store.list_requirements(run_id=run_id)]

    def get_requirement(self, requirement_id: str) -> dict[str, Any]:
        rec = self.store.get_requirement(requirement_id)
        if rec is None:
            raise NotFound("requirement not found", {"requirement_id": requirement_id})
        return self.requirement_view(rec)

    # ---- execution ----------------------------------------------------------------------------------
    def execute(self, run_id: str, requirement_ids: list[str] | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
        state = self.graphs.execution.invoke({
            "run_id": run_id, "requirement_ids": requirement_ids, "idempotency_key": idempotency_key, "trail": [],
        })
        outcome = state.get("outcome")
        if outcome == "run_not_found":
            raise RunNotFound("the run does not exist", {"run_id": run_id})
        if outcome == "invalid_selection":
            raise Conflict(state.get("reason") or "requirements are not executable", state.get("details") or {})
        if outcome == "no_confirmed_requirements":
            raise Conflict("no confirmed requirement exists for this run; confirm at least one first", {"run_id": run_id})
        view = self.get_verification(state["verification_id"])
        view["replayed"] = outcome == "replayed"
        view["workflow"] = {"path": state.get("trail", [])}
        return view

    def select_requirements(self, run_id: str, requirement_ids: list[str] | None) -> tuple[list[dict[str, Any]], str | None, dict[str, Any]]:
        """Executable (confirmed) requirement records for the run, or (``[]``, reason, details)."""
        all_recs = self.store.list_requirements(run_id=run_id)
        is_confirmed = lambda r: r["requirement"].get("source") == RequirementSource.developer_confirmed.value \
            and r["lifecycle_status"] in (rv.CONFIRMED, rv.VERIFIED, rv.FAILED, rv.UNKNOWN)
        if requirement_ids is None:
            chosen = [r for r in all_recs if is_confirmed(r)]
            return chosen, ("no_confirmed_requirements" if not chosen else None), {}
        by_id = {r["requirement_id"]: r for r in all_recs}
        bad = {rid: ("not_found_for_run" if rid not in by_id else "not_confirmed")
               for rid in requirement_ids if rid not in by_id or not is_confirmed(by_id[rid])}
        if bad:
            return [], "some requirements cannot be executed", {"requirements": bad}
        return [by_id[rid] for rid in dict.fromkeys(requirement_ids)], None, {}

    def run_engine(
        self, run_id: str, records: list[dict[str, Any]], prepared: PreparedEvidence, verification_id: str
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Run the deterministic engine over confirmed requirements. Returns (output, blocked)."""
        facts = prepared.facts
        blocked: dict[str, str] = {}
        reqs: list[dict[str, Any]] = []
        for rec in records:
            md = rec["requirement"].get("metadata") or {}
            scoped = md.get("environment_version")
            if md.get("run_id") != run_id:
                blocked[rec["requirement_id"]] = f"requirement is scoped to run {md.get('run_id')!r}, not {run_id!r}"
            elif scoped and facts.environment_version != scoped:
                blocked[rec["requirement_id"]] = (
                    f"environment version mismatch: requirement scoped to {scoped!r}, "
                    f"run used {facts.environment_version!r}")
            reqs.append(rec["requirement"])
        statements = list(dict.fromkeys(r["source_statement"] for r in records))
        raw_input = {
            **prepared.evidence.payload,
            "developer_intent": " ".join(statements)[:4000],
            "confirmed_requirements": reqs,
            "requirement_blocks": blocked,
            "pass_blockers": rv.pass_blockers(list(facts.missing_evidence)),
            "verification_id": verification_id,
            "investigate": False,
        }
        state = run_verification_state(raw_input, model_client=None)  # no model: verdicts are deterministic
        output = dict(state.output or {})
        if not output:
            raise LifecycleError("the verification engine produced no output")
        return output, blocked

    def persist_verification(
        self, run_id: str, records: list[dict[str, Any]], prepared: PreparedEvidence, output: dict[str, Any],
        verification_id: str, key: str,
    ) -> dict[str, Any]:
        payload = prepared.evidence.payload
        ev = payload.get("execution_evidence") or {}
        refs: list[str] = []
        for r in (output.get("requirements") or {}).values():
            refs += [x for x in (r.get("evidence_refs") or []) if isinstance(x, str)]
        traceability = {
            "run_id": run_id, "environment_id": ev.get("environment_id"), "environment_version": ev.get("environment_version"),
            "evidence_fingerprint": prepared.fingerprint,
            "episode_ids": [e.get("episode_id") for e in ev.get("episodes", [])][:1000],
            "event_ids": [e.get("event_id") for e in ev.get("events", []) if e.get("event_id")],
            "metric_ids": [m.get("id") for m in ev.get("metrics", []) if m.get("id")],
            "checkpoint_ids": [c.get("checkpoint_id") for c in ev.get("checkpoints", [])],
            "step_count": (ev.get("training_summary") or {}).get("step_count"),
            "training_summary": ev.get("training_summary"),
            "evidence_refs": list(dict.fromkeys(refs)),
            "missing_evidence": list(prepared.evidence.missing_evidence),
            "evidence_complete": ev.get("evidence_complete"),
            "warnings": list(prepared.evidence.warnings),
        }
        rec = {
            "verification_id": verification_id, "run_id": run_id,
            "intent_id": records[0]["intent_id"] if len({r["intent_id"] for r in records}) == 1 else None,
            "environment_id": ev.get("environment_id"), "environment_version": ev.get("environment_version"),
            "overall_status": output.get("overall_status", "unknown"), "contract_status": output.get("contract_status"),
            "idempotency_key": key, "requirement_ids": [r["requirement_id"] for r in records],
            "traceability": traceability, "output": output,
        }
        results = list((output.get("requirements") or {}).values())
        return self.store.save_verification(rec, results)

    # ---- incident handoff ------------------------------------------------------------------------------
    def handoff(self, verification_id: str) -> dict[str, Any]:
        """Idempotent Person 3 -> Person 4 handoff built from the *persisted* verification."""
        ver = self.store.get_verification(verification_id)
        if ver is None:
            raise NotFound("verification not found", {"verification_id": verification_id})
        link = self.store.get_link(verification_id)
        if link and link["handoff_status"] in ("created", "not_required"):
            return link
        output = ver["output"]
        incident_id = incident_id_for(verification_id)
        try:
            draft = build_incident_draft(output, run_id=ver["run_id"], incident_id=incident_id)
        except Exception as exc:  # noqa: BLE001 - never lose the verification
            logger.warning("incident draft failed for %s: %s", verification_id, type(exc).__name__)
            return self.store.upsert_link(verification_id, ver["run_id"], handoff_status="failed",
                                          error_code=type(exc).__name__, attempt=True)
        if draft is None:
            return self.store.upsert_link(verification_id, ver["run_id"], handoff_status="not_required")
        failed_ids = list(draft.details.get("failed_requirement_ids") or [])
        try:
            stored = self.sink.record(draft)
        except Exception as exc:  # noqa: BLE001 - incident service failure must not erase the verification
            logger.warning("incident handoff failed for %s: %s", verification_id, type(exc).__name__)
            return self.store.upsert_link(verification_id, ver["run_id"], handoff_status="failed",
                                          failed_requirement_ids=failed_ids, error_code=type(exc).__name__, attempt=True)
        return self.store.upsert_link(verification_id, ver["run_id"], handoff_status="created",
                                      incident_id=stored.get("incident_id", incident_id),
                                      failed_requirement_ids=failed_ids, attempt=True)

    def retry_handoff(self, verification_id: str) -> dict[str, Any]:
        self.handoff(verification_id)
        return self.get_verification(verification_id)

    # ---- reads -------------------------------------------------------------------------------------------
    def get_verification(self, verification_id: str) -> dict[str, Any]:
        ver = self.store.get_verification(verification_id)
        if ver is None:
            raise NotFound("verification not found", {"verification_id": verification_id})
        return self._verification_view(ver)

    def list_verifications(self, run_id: str) -> list[dict[str, Any]]:
        self._require_run(run_id)
        return [self._verification_view(v, include_output=False) for v in self.store.list_verifications(run_id)]

    def get_results(self, verification_id: str) -> list[dict[str, Any]]:
        if self.store.get_verification(verification_id) is None:
            raise NotFound("verification not found", {"verification_id": verification_id})
        return self._result_views(verification_id)

    def _result_views(self, verification_id: str) -> list[dict[str, Any]]:
        reqs = {r["requirement_id"]: r for r in self._reqs_for(verification_id)}
        order = {rid: i for i, rid in enumerate(reqs)}  # the order the requirements were verified in
        out = []
        for r in sorted(self.store.get_results(verification_id), key=lambda x: order.get(x["requirement_id"], len(order))):
            rq = reqs.get(r["requirement_id"]) or {}
            out.append({**r, "description": rq.get("description"), "category": rq.get("category"),
                        "source_statement": rq.get("source_statement")})
        return out

    def _reqs_for(self, verification_id: str) -> list[dict[str, Any]]:
        ver = self.store.get_verification(verification_id) or {}
        return [r for rid in ver.get("requirement_ids", []) if (r := self.store.get_requirement(rid)) is not None]

    def _verification_view(self, ver: dict[str, Any], *, include_output: bool = True) -> dict[str, Any]:
        link = self.store.get_link(ver["verification_id"])
        view: dict[str, Any] = {
            "verification_id": ver["verification_id"], "run_id": ver["run_id"], "intent_id": ver.get("intent_id"),
            "environment_id": ver.get("environment_id"), "environment_version": ver.get("environment_version"),
            "overall_status": ver["overall_status"], "contract_status": ver.get("contract_status"),
            "requirement_ids": ver["requirement_ids"], "traceability": ver["traceability"],
            "incident": None if link is None else {
                "handoff_status": link["handoff_status"], "incident_id": link.get("incident_id"),
                "failed_requirement_ids": link["failed_requirement_ids"], "error_code": link.get("error_code"),
                "attempts": link["attempts"]},
            "created_at": ver["created_at"],
        }
        if include_output:
            view["results"] = self._result_views(ver["verification_id"])
            out = ver["output"]
            view["summary"] = {"details": out.get("details"), "warnings": out.get("warnings", []), "error": out.get("error")}
        return view


def _now() -> str:
    from backend.database.utils import utc_now_iso

    return utc_now_iso()


__all__ = [
    "Conflict", "InvalidRequest", "LifecycleError", "NotFound", "OVERRIDABLE", "PreparedEvidence", "RunNotFound",
    "VerificationLifecycle", "evidence_fingerprint", "incident_id_for",
]
