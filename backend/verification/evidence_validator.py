"""Evidence extraction, validation, and bounded bundling for verification.

This module is the single place that turns the developer-supplied
``execution_evidence`` dictionary into typed, validated values that the
deterministic checkers and the (optional) Meta AI investigator consume.

Rules enforced here:

* **No fabrication.**  A value that is absent stays ``None``.  A reward is
  never defaulted to ``0.0``; an event list is never invented.
* **Absence is distinguishable from emptiness.**  ``events`` is ``None`` when
  no event evidence was supplied at all, and ``[]`` when the caller explicitly
  supplied an empty (but complete) event list.
* **Evidence identifiers are preserved.**  Real event IDs / observation IDs are
  carried through so that check results can reference them.
* **Bounds.**  Evidence passed to a model is windowed and size-limited; raw
  unbounded payloads are never handed to the provider.

The module performs no network access and no LLM calls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

#: Maximum number of events included in a model-facing evidence bundle.
DEFAULT_MAX_EVENTS = 50

#: Maximum number of metric observations included in a bundle.
DEFAULT_MAX_METRICS = 50

#: Maximum serialized characters for a single evidence value in a bundle.
DEFAULT_MAX_VALUE_CHARS = 512

#: Keys whose values must never be forwarded to a model provider.
SENSITIVE_KEY_MARKERS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "bearer",
        "credential",
        "password",
        "secret",
        "token",
    }
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite_or_none(value: Any) -> float | None:
    """Return *value* as a finite float, or ``None`` if unusable."""
    if not _is_number(value):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _as_dict(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _as_list_of_dicts(value: Any) -> list[dict[str, Any]] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return None
    return [dict(item) for item in value if isinstance(item, dict)]


def _refs_from_records(
    records: list[dict[str, Any]] | None,
    id_keys: tuple[str, ...] = ("event_id", "id", "observation_id"),
    prefix: str = "event",
) -> list[str]:
    """Collect real identifiers from evidence records.

    Records without an identifier are still referenced by their stable
    positional index *within the supplied evidence list*, which is real
    provenance (``event[2]``) rather than an invented value.
    """
    refs: list[str] = []
    if not records:
        return refs
    for index, record in enumerate(records):
        identifier = None
        for key in id_keys:
            candidate = record.get(key)
            if isinstance(candidate, str) and candidate.strip():
                identifier = candidate.strip()
                break
        refs.append(identifier or f"{prefix}[{index}]")
    return refs


@dataclass
class EvidenceBundle:
    """Typed view over the developer-supplied ``execution_evidence`` dict."""

    run_identifier: str | None = None
    environment_identifier: str | None = None
    environment_version: str | None = None

    configured_reward: float | None = None
    observed_reward: float | None = None

    episode: dict[str, Any] | None = None
    #: ``None`` means "no event evidence supplied"; ``[]`` means "explicitly
    #: empty but complete event list".
    events: list[dict[str, Any]] | None = None
    metrics: list[Any] = field(default_factory=list)

    environment_config: dict[str, Any] = field(default_factory=dict)
    training_config: dict[str, Any] = field(default_factory=dict)

    evidence_complete: bool = False
    reward_evidence_refs: list[str] = field(default_factory=list)
    event_evidence_refs: list[str] = field(default_factory=list)
    metric_evidence_refs: list[str] = field(default_factory=list)
    episode_evidence_refs: list[str] = field(default_factory=list)

    problems: list[str] = field(default_factory=list)

    @property
    def has_any_evidence(self) -> bool:
        return any(
            [
                self.observed_reward is not None,
                self.episode is not None,
                self.events is not None,
                bool(self.metrics),
            ]
        )

    def config_view(self) -> dict[str, Any]:
        """Flattened configuration mapping used by the configuration checker."""
        merged: dict[str, Any] = {}
        merged.update(self.environment_config)
        merged.update(self.training_config)
        return merged


_EVENT_COMPLETE_MARKERS: tuple[str, ...] = (
    "evidence_complete",
    "run_completed",
    "training_completed",
    "events_complete",
)


def extract_evidence(
    execution_evidence: Any,
    *,
    environment_config: dict[str, Any] | None = None,
    training_config: dict[str, Any] | None = None,
) -> EvidenceBundle:
    """Build an :class:`EvidenceBundle` from raw execution evidence.

    ``execution_evidence`` is untrusted input: every access is defensive and
    nothing is coerced into a value that looks like real evidence.
    """
    bundle = EvidenceBundle(
        environment_config=dict(environment_config or {}),
        training_config=dict(training_config or {}),
    )
    data = _as_dict(execution_evidence) or {}

    for attr in ("run_identifier", "run_id"):
        value = data.get(attr)
        if isinstance(value, str) and value.strip():
            bundle.run_identifier = value.strip()
            break
    for attr in ("environment_identifier", "environment_id"):
        value = data.get(attr)
        if isinstance(value, str) and value.strip():
            bundle.environment_identifier = value.strip()
            break
    value = data.get("environment_version")
    if isinstance(value, str) and value.strip():
        bundle.environment_version = value.strip()

    # ---- Reward -----------------------------------------------------------
    reward = data.get("reward")
    if isinstance(reward, dict):
        expected = _finite_or_none(reward.get("expected"))
        observed = _finite_or_none(reward.get("observed"))
        if reward.get("expected") is not None and expected is None:
            bundle.problems.append(
                "reward.expected is present but not a finite number; treated as unavailable"
            )
        if reward.get("observed") is not None and observed is None:
            bundle.problems.append(
                "reward.observed is present but not a finite number; treated as unavailable"
            )
        bundle.configured_reward = expected
        bundle.observed_reward = observed
        reward_ref = reward.get("event_id") or reward.get("evidence_id")
        if isinstance(reward_ref, str) and reward_ref.strip():
            bundle.reward_evidence_refs.append(reward_ref.strip())
        elif observed is not None:
            bundle.reward_evidence_refs.append("reward.observed")
    elif _is_number(reward):
        # A bare numeric reward carries no expectation and no identifier; it can
        # be compared only against an explicit requirement.
        bundle.observed_reward = _finite_or_none(reward)
        if bundle.observed_reward is not None:
            bundle.reward_evidence_refs.append("reward.observed")

    # ---- Episode ----------------------------------------------------------
    episode = _as_dict(data.get("episode"))
    if episode is None:
        episodes = _as_list_of_dicts(data.get("episodes"))
        if episodes:
            episode = episodes[-1]
    bundle.episode = episode
    if episode is not None:
        for key in ("episode_id", "id"):
            candidate = episode.get(key)
            if isinstance(candidate, str) and candidate.strip():
                bundle.episode_evidence_refs.append(candidate.strip())
                break
        else:
            bundle.problems.append(
                "episode evidence has no episode_id/id; no evidence reference can "
                "be attached to its result"
            )

    # ---- Events -----------------------------------------------------------
    raw_events = data.get("events")
    events = _as_list_of_dicts(raw_events)
    if raw_events is not None and events is None:
        bundle.problems.append("events is present but is not a list of objects")
    bundle.events = events
    bundle.event_evidence_refs = _refs_from_records(events)

    # ---- Metrics ----------------------------------------------------------
    raw_metrics = data.get("metrics")
    if raw_metrics is None:
        raw_metrics = data.get("observations")
    if isinstance(raw_metrics, list):
        bundle.metrics = list(raw_metrics)
    bundle.metric_evidence_refs = _refs_from_records(
        [m for m in bundle.metrics if isinstance(m, dict)],
        id_keys=("observation_id", "id", "metric_id"),
        prefix="metric",
    )

    # ---- Completeness -----------------------------------------------------
    bundle.evidence_complete = bool(data.get("evidence_complete") is True)
    if not bundle.evidence_complete:
        bundle.evidence_complete = any(data.get(key) is True for key in _EVENT_COMPLETE_MARKERS)

    return bundle


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_evidence(
    execution_evidence: Any,
    *,
    max_events: int = DEFAULT_MAX_EVENTS,
    max_metrics: int = DEFAULT_MAX_METRICS,
) -> list[str]:
    """Return a list of human-readable evidence problems.

    An empty list means the evidence is structurally usable.  Problems are
    advisory: they are surfaced as warnings, never converted into a PASS.
    """
    problems: list[str] = []
    if execution_evidence is None:
        return problems
    if not isinstance(execution_evidence, dict):
        return ["execution_evidence must be an object"]

    reward = execution_evidence.get("reward")
    if reward is not None and not isinstance(reward, (dict, int, float)):
        problems.append("reward must be an object or number")
    if isinstance(reward, dict):
        for key in ("expected", "observed"):
            value = reward.get(key)
            if value is None:
                continue
            if not _is_number(value):
                problems.append(f"reward.{key} must be numeric")
            elif _finite_or_none(value) is None:
                problems.append(f"reward.{key} must be finite")

    events = execution_evidence.get("events")
    if events is not None:
        if not isinstance(events, list):
            problems.append("events must be a list")
        elif len(events) > max_events:
            problems.append(
                f"events exceeds the bound of {max_events} records; only the first "
                f"{max_events} are used"
            )
        else:
            for index, event in enumerate(events):
                if not isinstance(event, dict):
                    problems.append(f"events[{index}] must be an object")

    metrics = execution_evidence.get("metrics")
    if metrics is not None:
        if not isinstance(metrics, list):
            problems.append("metrics must be a list")
        elif len(metrics) > max_metrics:
            problems.append(
                f"metrics exceeds the bound of {max_metrics} records; only the first "
                f"{max_metrics} are used"
            )

    episode = execution_evidence.get("episode")
    if episode is not None and not isinstance(episode, dict):
        problems.append("episode must be an object")

    return problems


# ---------------------------------------------------------------------------
# Redaction and bounded bundling for the model provider
# ---------------------------------------------------------------------------


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_KEY_MARKERS)


def redact(value: Any, *, _depth: int = 0) -> Any:
    """Return a copy of *value* with sensitive keys removed.

    Depth and string length are bounded so that a hostile payload cannot
    exhaust memory or smuggle unbounded text into a prompt.
    """
    if _depth > 6:
        return "<truncated>"
    if isinstance(value, dict):
        return {
            str(key): redact(item, _depth=_depth + 1)
            for key, item in value.items()
            if not _is_sensitive_key(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, _depth=_depth + 1) for item in value]
    if isinstance(value, str):
        if len(value) > DEFAULT_MAX_VALUE_CHARS:
            return value[:DEFAULT_MAX_VALUE_CHARS] + "...<truncated>"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:DEFAULT_MAX_VALUE_CHARS]


def build_investigation_bundle(
    *,
    incident_requirement_ids: list[str],
    bundle: EvidenceBundle,
    check_results: dict[str, Any] | None = None,
    max_events: int = DEFAULT_MAX_EVENTS,
    max_metrics: int = DEFAULT_MAX_METRICS,
) -> dict[str, Any]:
    """Build a bounded, redacted evidence bundle for the Meta AI investigator.

    Only facts that were actually supplied are included; missing evidence is
    reported explicitly in ``missing_evidence`` instead of being invented.
    """
    missing: list[str] = []
    events = None
    if bundle.events is None:
        missing.append("execution events (no event evidence supplied)")
    else:
        events = bundle.events[:max_events]

    metrics = list(bundle.metrics[:max_metrics])
    if not metrics:
        missing.append("metric observations (none supplied)")
    if bundle.observed_reward is None:
        missing.append("observed reward (none supplied)")
    if bundle.episode is None:
        missing.append("episode outcome (none supplied)")
    if bundle.environment_version is None:
        missing.append("environment version (not supplied)")

    facts: list[dict[str, Any]] = []
    if bundle.observed_reward is not None:
        fact: dict[str, Any] = {"fact": "observed_reward", "value": bundle.observed_reward}
        if bundle.reward_evidence_refs:
            fact["evidence_refs"] = list(bundle.reward_evidence_refs)
        facts.append(fact)
    if bundle.configured_reward is not None:
        facts.append(
            {
                "fact": "configured_reward",
                "value": bundle.configured_reward,
                "evidence_refs": list(bundle.reward_evidence_refs),
            }
        )
    if bundle.episode is not None:
        facts.append(
            {
                "fact": "episode_outcome",
                "value": redact(bundle.episode),
                "evidence_refs": list(bundle.episode_evidence_refs),
            }
        )

    results_payload: list[dict[str, Any]] = []
    for requirement_id, result in (check_results or {}).items():
        status = getattr(result, "status", None)
        results_payload.append(
            {
                "requirement_id": requirement_id,
                "status": getattr(status, "value", status),
                "expected": getattr(result, "expected", None),
                "actual": getattr(result, "actual", None),
                "evidence_refs": list(getattr(result, "evidence_refs", []) or []),
                "details": redact(getattr(result, "details", None)),
            }
        )

    return {
        "incident_requirement_ids": list(incident_requirement_ids),
        "run_identifier": bundle.run_identifier,
        "environment_identifier": bundle.environment_identifier,
        "environment_version": bundle.environment_version,
        "observed_facts": facts,
        "events": redact(events) if events is not None else None,
        "metric_observations": redact(metrics),
        "check_results": results_payload,
        "configuration": redact(bundle.config_view()),
        "missing_evidence": missing,
        "evidence_problems": list(bundle.problems),
    }


__all__ = [
    "DEFAULT_MAX_EVENTS",
    "DEFAULT_MAX_METRICS",
    "EvidenceBundle",
    "build_investigation_bundle",
    "extract_evidence",
    "redact",
    "validate_evidence",
]
