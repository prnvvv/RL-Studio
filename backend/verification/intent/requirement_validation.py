"""Deterministic validation of proposed requirements against the real run evidence.

Nothing here calls a model. A model may *propose* a requirement; this module decides whether the
proposal is supported, scoped to the right run/environment version, evaluable from the evidence that
actually exists, and consistent with the other requirements. It never invents an expected value and
never converts missing evidence into a pass.

Validation statuses
    valid               supported, in scope and evaluable
    needs_clarification a criterion/threshold the user did not state (never guessed)
    invalid             unsupported type, wrong scope/version, or contradictory
    not_evaluable       well formed, but the run has no evidence this requirement could be judged by
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from backend.verification.models import RequirementType, VerificationRequirement

# ---- lifecycle ---------------------------------------------------------------------------------
DRAFT = "draft"
NEEDS_CLARIFICATION = "needs_clarification"
CONFIRMED = "confirmed"
REJECTED = "rejected"
INVALID = "invalid"
VERIFIED = "verified"
FAILED = "failed"
UNKNOWN = "unknown"
LIFECYCLE_STATES = (DRAFT, NEEDS_CLARIFICATION, CONFIRMED, REJECTED, INVALID, VERIFIED, FAILED, UNKNOWN)

V_VALID = "valid"
V_INVALID = "invalid"
V_CLARIFY = "needs_clarification"
V_NOT_EVALUABLE = "not_evaluable"

SUPPORTED_TYPES = (
    RequirementType.reward,
    RequirementType.termination,
    RequirementType.event,
    RequirementType.metric,
    RequirementType.configuration,
)
OPERATORS = ("==", "!=", ">=", "<=", ">", "<")
#: Event types the Studio pipeline actually emits (see ``backend.studio.provenance_bridge``).
#: A requirement about any other event can never be satisfied *or* violated by this evidence.
STUDIO_EMITTED_EVENTS = frozenset({
    "run_started", "run_resumed", "episode_end", "checkpoint_saved",
    "run_completed", "run_interrupted", "run_failed",
})
TERMINATION_OUTCOMES = {
    "terminated": "terminated", "termination": "terminated", "done": "terminated",
    "goal_reached": "goal_reached", "goal_attained": "goal_reached", "success": "goal_reached",
    "truncated": "truncated", "time_limit": "truncated",
}

#: How each requirement type is judged, in words the user sees in the explanation.
EVIDENCE_REQUIRED = {
    "reward": ["episodes[-1].reward (final episode total reward)"],
    "termination": ["episodes[-1] termination/truncation/goal flags or length"],
    "event": ["canonical run events"],
    "metric": ["metric observations of the named metric"],
    "configuration": ["run configuration snapshot"],
}


@dataclass
class ValidationOutcome:
    status: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reasons": self.reasons, "warnings": self.warnings, "checks": self.checks}


# ---- text helpers ------------------------------------------------------------------------------
_NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def normalize_ws(text: str) -> str:
    return " ".join(text.split())


def numbers_in(text: str) -> list[float]:
    out: list[float] = []
    for m in _NUMBER.findall(text):
        try:
            out.append(float(m))
        except ValueError:
            continue
    return out


def statement_states_number(statement: str, value: Any) -> bool:
    """True only if the user's own words contain this number (so a threshold is never invented)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return False
    return any(math.isclose(n, float(value), rel_tol=1e-9, abs_tol=1e-12) for n in numbers_in(statement))


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


# ---- evidence facts ----------------------------------------------------------------------------
def flatten_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Scalar configuration of the run as dotted keys (+ bare aliases when unambiguous)."""
    groups = {
        "env_params": payload.get("environment_config") or {},
        "training": {k: v for k, v in (payload.get("training_config") or {}).items() if k != "agent_params"},
        "agent_params": (payload.get("training_config") or {}).get("agent_params") or {},
    }
    flat: dict[str, Any] = {}
    seen: dict[str, list[str]] = {}
    for group, values in groups.items():
        for key, value in values.items():
            if isinstance(value, (str, int, float, bool)):
                flat[f"{group}.{key}"] = value
                seen.setdefault(key, []).append(group)
    for key, owners in seen.items():
        if len(owners) == 1 and key not in flat:
            flat[key] = flat[f"{owners[0]}.{key}"]
    return flat


@dataclass(frozen=True)
class EvidenceFacts:
    run_id: str | None
    environment_id: str | None
    environment_version: str | None
    episode_count: int
    event_count: int
    event_types: frozenset[str]
    metric_names: frozenset[str]
    metric_count: int
    config: dict[str, Any]
    missing_evidence: tuple[str, ...]

    @classmethod
    def from_payload(cls, payload: dict[str, Any], missing: list[str]) -> EvidenceFacts:
        ev = payload.get("execution_evidence") or {}
        metrics = [m for m in (ev.get("metrics") or []) if isinstance(m, dict)]
        events = [e for e in (ev.get("events") or []) if isinstance(e, dict)]
        return cls(
            run_id=ev.get("run_id"),
            environment_id=ev.get("environment_id"),
            environment_version=ev.get("environment_version"),
            episode_count=len(ev.get("episodes") or []),
            event_count=len(events),
            event_types=frozenset(str(e.get("event_type")) for e in events if e.get("event_type")),
            metric_names=frozenset(str(m.get("metric_name") or m.get("name")) for m in metrics if m.get("metric_name") or m.get("name")),
            metric_count=len(metrics),
            config=flatten_config(payload),
            missing_evidence=tuple(missing),
        )

    def describe(self) -> dict[str, Any]:
        """Bounded, secret-free capability catalogue shown to the model and to the user."""
        return {
            "environment_id": self.environment_id,
            "environment_version": self.environment_version,
            "episodes_recorded": self.episode_count,
            "metric_names": sorted(self.metric_names),
            "emitted_event_types": sorted(STUDIO_EMITTED_EVENTS),
            "config_keys": sorted(self.config)[:80],
        }


# ---- pass blockers (evidence completeness gate) --------------------------------------------------
_GLOBAL_BLOCKERS = ("run_not_completed", "run_error_recorded", "no_episodes", "environment_version_mismatch",
                    "environment_version_missing", "run_not_registered_in_provenance")
_EVENT_BLOCKERS = ("no_canonical_events", "episode_events_incomplete", "events_truncated")
_METRIC_BLOCKERS = ("metrics_truncated",)


def pass_blockers(missing: list[str]) -> dict[str, list[str]]:
    """Which missing-evidence entries forbid a PASS, by requirement type ("all" applies to every one)."""
    def pick(prefixes: tuple[str, ...]) -> list[str]:
        return [m for m in missing if any(m == p or m.startswith(p + ":") for p in prefixes)]

    return {"all": pick(_GLOBAL_BLOCKERS), "event": pick(_EVENT_BLOCKERS), "metric": pick(_METRIC_BLOCKERS)}


# ---- single requirement ---------------------------------------------------------------------------
def _check(out: ValidationOutcome, name: str, ok: bool, detail: str) -> bool:
    out.checks.append({"check": name, "ok": ok, "detail": detail})
    return ok


def validate_proposal(
    req: VerificationRequirement,
    facts: EvidenceFacts,
    *,
    run_id: str,
    source_statement: str,
    user_statement: str,
) -> ValidationOutcome:
    out = ValidationOutcome(status=V_VALID)
    md = req.metadata or {}

    def fail(status: str, reason: str) -> ValidationOutcome:
        if out.status == V_VALID or status == V_INVALID:
            out.status = status
        out.reasons.append(reason)
        return out

    # supported type
    if req.type not in SUPPORTED_TYPES:
        _check(out, "type_supported", False, f"{req.type.value} is not a verifiable category")
        return fail(V_INVALID, f"unsupported requirement type: {req.type.value}")
    _check(out, "type_supported", True, req.type.value)

    # provenance of the wording
    if not source_statement.strip() or normalize_ws(source_statement).lower() not in normalize_ws(user_statement).lower():
        _check(out, "source_in_user_statement", False, "the cited source text is not part of what the user wrote")
        return fail(V_INVALID, "source statement is not present in the original user statement")
    _check(out, "source_in_user_statement", True, "cited text found in the original statement")

    # scope: run + environment version
    scoped_run = md.get("run_id")
    if scoped_run != run_id or (facts.run_id and facts.run_id != run_id):
        _check(out, "run_scope", False, f"requirement run {scoped_run!r} != {run_id!r}")
        return fail(V_INVALID, "requirement is scoped to a different run")
    _check(out, "run_scope", True, run_id)
    if facts.environment_version is None:
        _check(out, "environment_version", False, "the run has no recorded environment version")
        fail(V_NOT_EVALUABLE, "environment version of the run is unknown, so version scope cannot be confirmed")
    else:
        stated = md.get("environment_version")
        if stated and stated != facts.environment_version:
            _check(out, "environment_version", False, f"{stated!r} != run version {facts.environment_version!r}")
            return fail(V_INVALID, f"environment version mismatch: requirement for {stated!r}, run used {facts.environment_version!r}")
        _check(out, "environment_version", True, facts.environment_version)

    op = req.comparison_operator
    if op is not None and op not in OPERATORS:
        return fail(V_INVALID, f"unsupported comparison operator {op!r}")

    t = req.type
    if t is RequirementType.reward or t is RequirementType.metric:
        if t is RequirementType.metric:
            name = md.get("metric_name")
            if not name:
                _check(out, "metric_named", False, "no metric named")
                fail(V_CLARIFY, "which metric should be compared was not stated")
            elif name not in facts.metric_names:
                _check(out, "metric_recorded", False, f"{name!r} not in {sorted(facts.metric_names)}")
                fail(V_NOT_EVALUABLE, f"metric {name!r} is not recorded for this run (recorded: {sorted(facts.metric_names) or 'none'})")
            else:
                _check(out, "metric_recorded", True, name)
        elif facts.episode_count == 0:
            _check(out, "episodes_available", False, "no episodes recorded")
            fail(V_NOT_EVALUABLE, "the run recorded no episodes, so no reward was observed")
        if not is_finite_number(req.expected_value):
            _check(out, "expected_value_stated", False, "no numeric threshold")
            fail(V_CLARIFY, "no numeric expected value was stated; none is assumed")
        elif not statement_states_number(user_statement, req.expected_value):
            _check(out, "expected_value_stated", False, f"{req.expected_value} does not appear in the statement")
            fail(V_CLARIFY, f"expected value {req.expected_value} is not stated by the user")
        else:
            _check(out, "expected_value_stated", True, str(req.expected_value))
        if op is None:
            fail(V_CLARIFY, "no comparison (==, >=, <=, ...) was stated")
    elif t is RequirementType.termination:
        steps = md.get("max_steps")
        outcome = TERMINATION_OUTCOMES.get(str(req.expected_value).strip().lower().replace(" ", "_")) if isinstance(req.expected_value, str) else None
        if steps is not None:
            if not (isinstance(steps, int) and not isinstance(steps, bool) and steps > 0) or not statement_states_number(user_statement, steps):
                _check(out, "max_steps_stated", False, f"{steps!r}")
                fail(V_CLARIFY, "a step limit must be a positive integer that the user stated")
            else:
                _check(out, "max_steps_stated", True, str(steps))
                if op != "<=":
                    _check(out, "step_limit_is_upper_bound", False, f"operator {op!r}")
                    fail(V_CLARIFY, "only an upper bound ('at most N steps', operator <=) is supported for step limits")
        elif outcome is None:
            _check(out, "outcome_supported", False, f"{req.expected_value!r}")
            fail(V_CLARIFY, f"episode outcome must be one of {sorted(set(TERMINATION_OUTCOMES.values()))} or a step limit")
        else:
            _check(out, "outcome_supported", True, outcome)
        if facts.episode_count == 0:
            _check(out, "episodes_available", False, "no episodes recorded")
            fail(V_NOT_EVALUABLE, "the run recorded no episodes")
    elif t is RequirementType.event:
        names = [n for n in (md.get("required_event"), md.get("forbidden_event")) if n]
        if not names:
            fail(V_CLARIFY, "no event was named")
        for n in names:
            if n not in STUDIO_EMITTED_EVENTS:
                _check(out, "event_observable", False, f"{n!r} is not emitted by the Studio pipeline")
                fail(V_NOT_EVALUABLE, f"event {n!r} is never emitted by this pipeline, so its absence or presence proves nothing "
                                      f"(observable: {sorted(STUDIO_EMITTED_EVENTS)})")
            else:
                _check(out, "event_observable", True, n)
        if facts.event_count == 0:
            _check(out, "events_available", False, "no canonical events")
            fail(V_NOT_EVALUABLE, "the run has no canonical events")
    elif t is RequirementType.configuration:
        key = md.get("config_key")
        if not key:
            fail(V_CLARIFY, "which configuration setting was not stated")
        elif key not in facts.config:
            _check(out, "config_key_exists", False, f"{key!r}")
            fail(V_NOT_EVALUABLE, f"setting {key!r} is not in the recorded run configuration")
        else:
            _check(out, "config_key_exists", True, key)
        if req.expected_value is None:
            fail(V_CLARIFY, "no expected configuration value was stated")
        elif is_finite_number(req.expected_value) and not statement_states_number(user_statement, req.expected_value):
            fail(V_CLARIFY, f"expected value {req.expected_value} is not stated by the user")
        if op is None:
            fail(V_CLARIFY, "no comparison was stated")

    for blocker in pass_blockers(list(facts.missing_evidence)).get("all", []):
        out.warnings.append(f"evidence incomplete ({blocker}): a PASS cannot be reported until this is resolved")
    return out


# ---- contradictions across requirements ----------------------------------------------------------
def _target(req: VerificationRequirement) -> tuple[str, str] | None:
    md = req.metadata or {}
    if req.type is RequirementType.reward:
        return ("reward", "final_episode_reward")
    if req.type is RequirementType.metric and md.get("metric_name"):
        return ("metric", str(md["metric_name"]))
    if req.type is RequirementType.configuration and md.get("config_key"):
        return ("configuration", str(md["config_key"]))
    if req.type is RequirementType.termination and md.get("max_steps") is not None:
        return ("termination", "steps")
    return None


def _bounds(req: VerificationRequirement) -> tuple[float, bool, float, bool, list[float]] | None:
    v = req.expected_value
    if not is_finite_number(v):
        return None
    x, tol, op = float(v), float(req.tolerance or 0.0), req.comparison_operator or "=="
    if (req.metadata or {}).get("max_steps") is not None:
        op = "<="
    lo, lo_open, hi, hi_open, excl = -math.inf, False, math.inf, False, []
    if op == "==":
        lo, hi = x - tol, x + tol
    elif op == ">=":
        lo = x - tol
    elif op == ">":
        lo, lo_open = x + tol, True
    elif op == "<=":
        hi = x + tol
    elif op == "<":
        hi, hi_open = x - tol, True
    elif op == "!=":
        excl = [x]
    return lo, lo_open, hi, hi_open, excl


def find_contradictions(reqs: list[VerificationRequirement]) -> list[tuple[list[str], str]]:
    """Pairs/groups of requirements that cannot all hold. Purely numeric/logical, no model."""
    found: list[tuple[list[str], str]] = []
    by_target: dict[tuple[str, str], list[VerificationRequirement]] = {}
    for r in reqs:
        key = _target(r)
        if key is not None:
            by_target.setdefault(key, []).append(r)
    for (kind, name), group in by_target.items():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                ba, bb = _bounds(a), _bounds(b)
                if ba is None or bb is None:
                    continue
                lo, hi = max(ba[0], bb[0]), min(ba[2], bb[2])
                lo_open = (ba[1] and ba[0] == lo) or (bb[1] and bb[0] == lo)
                hi_open = (ba[3] and ba[2] == hi) or (bb[3] and bb[2] == hi)
                empty = lo > hi or (lo == hi and (lo_open or hi_open))
                if not empty and lo == hi:
                    empty = lo in ba[4] + bb[4]
                if empty:
                    found.append(([a.id, b.id], f"no value of {kind} '{name}' can satisfy both requirements"))
    ev = [r for r in reqs if r.type is RequirementType.event]
    for a in ev:
        for b in ev:
            if a is not b and (a.metadata or {}).get("required_event") and \
                    (a.metadata or {}).get("required_event") == (b.metadata or {}).get("forbidden_event"):
                found.append(([a.id, b.id], f"event {(a.metadata or {})['required_event']!r} is both required and forbidden"))
    return found


__all__ = [
    "CONFIRMED", "DRAFT", "EVIDENCE_REQUIRED", "FAILED", "INVALID", "LIFECYCLE_STATES", "NEEDS_CLARIFICATION",
    "REJECTED", "STUDIO_EMITTED_EVENTS", "TERMINATION_OUTCOMES", "UNKNOWN", "VERIFIED",
    "V_CLARIFY", "V_INVALID", "V_NOT_EVALUABLE", "V_VALID",
    "EvidenceFacts", "ValidationOutcome", "find_contradictions", "flatten_config", "is_finite_number",
    "normalize_ws", "numbers_in", "pass_blockers", "statement_states_number", "validate_proposal",
]
