"""Deterministic grounding of the model's advisory output.

The model may propose; this module decides what survives. Every rule here is plain code:

* A cited evidence reference must exist in the persisted-evidence index built from real records. Unknown references
  are removed and reported (``ungrounded_references``), never kept.
* An "observed fact" with no valid citation is not an observation; it is moved to ``unsupported_statements``.
* A hypothesis with no valid supporting evidence is ``speculative`` with confidence capped; no hypothesis ever
  becomes a confirmed root cause (``root_cause_status`` is only ``probable`` or ``unresolved``).
* Recovery options never execute and never lower the authorization requirement: any state-changing action requires
  user authorization regardless of what the model said. A checkpoint must be a real candidate and must not be in the
  incident's affected set. Actions the existing recovery executor cannot run say so (``executor_supported: false``).

Nothing here decides a verification verdict.
"""

from __future__ import annotations

from typing import Any

from .context import IncidentContext
from .models import RecoveryPlan, RootCauseAnalysis

#: confidence ceilings applied deterministically
SPECULATIVE_CONFIDENCE_CAP = 0.3
INCOMPLETE_EVIDENCE_CONFIDENCE_CAP = 0.7
ABSOLUTE_CONFIDENCE_CAP = 0.9
PROBABLE_THRESHOLD = 0.5

#: model action name -> existing ``RecoveryStrategy`` the Person 4 executor supports (None = not supported there)
STRATEGY_FOR_ACTION: dict[str, str | None] = {
    "restore_checkpoint": "restore_checkpoint",
    "resume_with_corrected_config": "correct_environment_config",
    "discard_trajectories": "discard_pending_rollouts",
    "regenerate_experiences": "continue_with_fresh_experience",
    "evaluate_only": "evaluate_only",
    "rescore_experiences": None,
    "restart_training": None,
    "no_action": None,
}
#: read-only actions that change nothing (everything else needs explicit user authorization)
NON_MUTATING_ACTIONS = frozenset({"evaluate_only", "no_action"})


def _split(refs: list[str], ctx: IncidentContext) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    for ref in dict.fromkeys(r.strip() for r in refs if isinstance(r, str) and r.strip()):
        (valid if ref in ctx.evidence_index else invalid).append(ref)
    return valid, invalid


def _merge(*groups: list[str]) -> list[str]:
    return list(dict.fromkeys(item for group in groups for item in group if item))


def ground_root_cause(analysis: RootCauseAnalysis, ctx: IncidentContext) -> dict[str, Any]:
    ungrounded: list[str] = []
    facts: list[dict[str, Any]] = []
    unsupported: list[str] = []
    for fact in analysis.observed_facts:
        valid, invalid = _split(fact.evidence_ids, ctx)
        ungrounded += invalid
        if valid:
            facts.append({"statement": fact.statement, "evidence_ids": valid, "kind": "observation"})
        else:
            unsupported.append(fact.statement)

    cap = INCOMPLETE_EVIDENCE_CONFIDENCE_CAP if ctx.missing_evidence else ABSOLUTE_CONFIDENCE_CAP
    hypotheses: list[dict[str, Any]] = []
    for hyp in analysis.hypotheses:
        supporting, bad_s = _split(hyp.supporting_evidence_ids, ctx)
        contradicting, bad_c = _split(hyp.contradicting_evidence_ids, ctx)
        ungrounded += bad_s + bad_c
        supported = bool(supporting)
        confidence = hyp.confidence
        if confidence is not None:
            confidence = min(confidence, cap if supported else SPECULATIVE_CONFIDENCE_CAP)
        hypotheses.append({
            "component": hyp.component, "description": hyp.description,
            "supporting_evidence_ids": supporting, "contradicting_evidence_ids": contradicting,
            "confidence": confidence, "uncertainty": hyp.uncertainty, "kind": "inference",
            "evidence_support": "supported" if supported else "speculative",
        })
    hypotheses.sort(key=lambda h: (h["evidence_support"] != "supported", -(h["confidence"] or 0)))

    leading = hypotheses[0] if hypotheses else None
    probable = bool(leading and leading["evidence_support"] == "supported"
                    and (leading["confidence"] or 0) >= PROBABLE_THRESHOLD)
    return {
        "summary": analysis.summary,
        "observed_facts": facts,
        "hypotheses": hypotheses,
        # the model can never confirm a cause: "confirmed" is reserved for deterministic evidence, not produced here
        "root_cause_status": "probable" if probable else "unresolved",
        "confirmed": False,
        "missing_evidence": _merge(ctx.missing_evidence, analysis.missing_evidence),
        "recommended_investigation": analysis.recommended_investigation,
        "limitations": _merge(analysis.limitations, [
            "Hypotheses are model inferences from the cited records, not confirmed root causes.",
        ]),
        "unsupported_statements": unsupported,
        "ungrounded_references": _merge(ungrounded),
    }


def ground_recovery(plan: RecoveryPlan, ctx: IncidentContext) -> dict[str, Any]:
    ungrounded: list[str] = []
    options: list[dict[str, Any]] = []
    for opt in plan.options:
        supporting, invalid = _split(opt.supporting_evidence_ids, ctx)
        ungrounded += invalid
        strategy = STRATEGY_FOR_ACTION.get(opt.action)
        blocked: str | None = None
        checkpoint = opt.target_checkpoint_id
        if checkpoint is not None:
            info = ctx.candidate_checkpoints.get(checkpoint)
            if info is None:
                ungrounded.append(checkpoint)
                checkpoint = None
                if opt.action == "restore_checkpoint":
                    blocked = "the proposed checkpoint is not a recorded checkpoint of this run"
            elif info["affected_by_incident"]:
                blocked = "the proposed checkpoint is in the incident's affected set"
            elif info["integrity_status"] != "verified":
                blocked = f"the proposed checkpoint's integrity is {info['integrity_status']}, not verified"
        elif opt.action == "restore_checkpoint":
            blocked = "no recorded checkpoint was identified"
        mutating = opt.action not in NON_MUTATING_ACTIONS
        options.append({
            "action": opt.action, "reason": opt.reason,
            "supporting_evidence_ids": supporting,
            "evidence_support": "supported" if supporting else "speculative",
            "target_checkpoint_id": checkpoint,
            "expected_impact": opt.expected_impact, "risks": opt.risks, "preconditions": opt.preconditions,
            # the model cannot waive authorization for anything that changes state
            "requires_user_authorization": True if mutating else opt.requires_user_authorization,
            "executed": False,
            "blocked_reason": blocked,
            "mapped_strategy": strategy,
            "executor_supported": strategy is not None,
            "next_step": (
                f"POST /api/v1/incidents/{ctx.incident_id}/recovery-assessments with recovery_strategy={strategy}"
                if strategy and not blocked else None),
        })
    return {
        "summary": plan.summary,
        "options": options,
        "not_recommended": plan.not_recommended,
        "missing_evidence": _merge(ctx.missing_evidence, plan.missing_evidence),
        "limitations": _merge(plan.limitations, [
            ("These are recommendations only. Nothing was executed; recovery runs through the existing "
             "assessment, approval and execution endpoints."),
        ]),
        "executed": False,
        "ungrounded_references": _merge(ungrounded),
    }
