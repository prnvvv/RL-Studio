"""Episode outcome verification checker.

Verifies episode-level requirements using episode evidence that was actually
recorded during execution.

Non-negotiable rules (AGENTS.md §4.4, §6):

* Missing evidence is ``UNKNOWN`` — never ``PASS``.
* Only real evidence identifiers are attached to the result.
* The ``details`` dict keeps the human-readable derivation; it never pretends
  to be an evidence identifier.
"""

from __future__ import annotations

import math
from typing import Any

from backend.verification.models import (
    CheckStatus,
    VerificationCheckResult,
    VerificationRequirement,
)

#: Event keys that may carry a termination signal.
TERMINATION_KEYS = ("terminated", "done", "termination", "episode_terminated")
#: Event keys that may carry a truncation signal.
TRUNCATION_KEYS = ("truncated", "truncate", "truncation")
#: Event keys that may carry a goal-attainment signal.
GOAL_KEYS = ("goal_attained", "goal_reached", "goal_achieved", "success")
#: Episode keys that may carry the observed episode length.
STEP_KEYS = ("steps", "length", "timestep")

_TRUTHY_STRINGS = {"true", "yes", "terminated", "truncated", "reached"}


def _as_bool(value: Any) -> bool | None:
    """Coerce an evidence value into a tri-state boolean.

    Returns ``None`` when the value carries no usable boolean signal.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUTHY_STRINGS:
            return True
        if lowered in {"false", "no", "none"}:
            return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    return None


def _find_flag(
    episode_data: dict[str, Any] | None,
    keys: tuple[str, ...],
) -> tuple[str, bool] | None:
    """Return ``(key, value)`` for the first present flag key, else ``None``."""
    if not episode_data:
        return None
    for key in keys:
        if key in episode_data:
            coerced = _as_bool(episode_data[key])
            if coerced is not None:
                return key, coerced
    return None


def _evidence_refs(
    episode_id: str | None,
    evidence_refs: list[str] | None,
) -> list[str]:
    """Collect only *real* evidence identifiers (no synthesised labels)."""
    refs: list[str] = []
    for ref in evidence_refs or []:
        if isinstance(ref, str) and ref and ref not in refs:
            refs.append(ref)
    if episode_id and episode_id not in refs:
        refs.append(episode_id)
    return refs


def _observed_steps(episode_data: dict[str, Any] | None) -> tuple[str, int] | None:
    """Return ``(key, steps)`` for the first recorded episode length, else ``None``.

    Only real recorded values are used; nothing is derived from the bound being
    checked.
    """
    if not isinstance(episode_data, dict):
        return None
    for key in STEP_KEYS:
        if key not in episode_data:
            continue
        value = episode_data[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not math.isfinite(float(value)):
            continue
        return key, int(value)
    return None


def _check_max_steps(
    requirement: VerificationRequirement,
    max_steps: int,
    episode_data: dict[str, Any] | None,
    refs: list[str],
    source: str,
) -> VerificationCheckResult:
    """Evaluate an episode-step bound against recorded episode length."""
    observed = _observed_steps(episode_data)
    if observed is None:
        return _result(
            requirement,
            CheckStatus.UNKNOWN,
            expected=max_steps,
            actual=None,
            evidence_refs=refs,
            note=(
                "No recorded episode length (steps/length/timestep) is available; "
                f"the {max_steps}-step bound cannot be evaluated"
            ),
            source=source,
            extra={"max_steps": max_steps},
        )

    key, steps = observed
    return _result(
        requirement,
        CheckStatus.PASS if steps <= max_steps else CheckStatus.FAIL,
        expected=max_steps,
        actual=steps,
        evidence_refs=refs,
        note=f"observed steps={steps} ({key}), max_steps={max_steps}",
        source=source,
        extra={"max_steps": max_steps, "steps_key": key},
    )


def _classify(
    termination: tuple[str, bool] | None,
    truncation: tuple[str, bool] | None,
    goal: tuple[str, bool] | None,
) -> str | None:
    """Derive the observed episode outcome from boolean evidence.

    Returns ``None`` when the available evidence does not determine an outcome.
    """
    goal_found = goal is not None and goal[1] is True
    term_found = termination is not None and termination[1] is True
    trunc_found = truncation is not None and truncation[1] is True

    if goal_found:
        return "goal_attained"
    if trunc_found:
        return "truncated"
    if term_found:
        return "terminated"
    return None


def _expected_outcome(expected: Any) -> str | None:
    """Normalise an expected episode outcome into the observed vocabulary."""
    if expected is True:
        return "terminated"
    if expected is False:
        return "not_terminated"
    if isinstance(expected, str):
        normalised = expected.strip().lower().replace(" ", "_")
        if normalised in {
            "goal_attained",
            "goal_reached",
            "success",
        }:
            return "goal_attained"
        if normalised in {"terminated", "termination", "done"}:
            return "terminated"
        if normalised in {"truncated", "truncation", "time_limit"}:
            return "truncated"
        if normalised in {"not_terminated", "not_truncated"}:
            return normalised
        return normalised
    return None


def _result(
    requirement: VerificationRequirement,
    status: CheckStatus,
    *,
    expected: Any,
    actual: Any,
    evidence_refs: list[str],
    note: str,
    source: str,
    extra: dict[str, Any] | None = None,
) -> VerificationCheckResult:
    details: dict[str, Any] = {"note": note, "source": source}
    if extra:
        details.update(extra)
    return VerificationCheckResult(
        requirement_id=requirement.id,
        status=status,
        expected=expected,
        actual=actual,
        tolerance=None,
        evidence_refs=list(evidence_refs),
        details=details,
        is_mandatory=requirement.is_mandatory,
    )


def execute_check(
    check_id: str,
    requirement: VerificationRequirement,
    *,
    episode_id: str | None = None,
    episode_data: dict[str, Any] | None = None,
    termination_observed: bool | None = None,
    truncation_observed: bool | None = None,
    goal_attained_observed: bool | None = None,
    max_steps: int | None = None,
    evidence_refs: list[str] | None = None,
    source: str = "episode_check",
) -> VerificationCheckResult:
    """Execute an episode outcome verification check.

    Args:
        check_id: Identifier for this check (provenance only).
        requirement: The ``VerificationRequirement`` describing the contract.
        episode_id: Identifier of the episode the evidence belongs to.  When
            provided it becomes a real evidence reference on the result.
        episode_data: Recorded episode summary dict.
        termination_observed: Explicit termination flag, when available.
        truncation_observed: Explicit truncation flag, when available.
        goal_attained_observed: Explicit goal-attainment flag, when available.
        max_steps: Optional step bound.  When provided, the recorded episode
            length (``steps``/``length``/``timestep``) is compared against it.
        evidence_refs: Additional real evidence identifiers.
        source: Provenance label recorded in ``details``.

    Returns:
        A ``VerificationCheckResult`` with status ``PASS``, ``FAIL`` or
        ``UNKNOWN``.
    """
    expected = requirement.expected_value
    refs = _evidence_refs(episode_id, evidence_refs)

    # ---- 0. Step bound ---------------------------------------------------
    if max_steps is not None:
        return _check_max_steps(requirement, max_steps, episode_data, refs, source)

    expected_outcome = _expected_outcome(expected)

    # ---- 1. Evidence collection -----------------------------------------
    explicit = (
        termination_observed is not None
        or truncation_observed is not None
        or goal_attained_observed is not None
    )

    termination: tuple[str, bool] | None = (
        ("termination_observed", termination_observed)
        if termination_observed is not None
        else None
    )
    truncation: tuple[str, bool] | None = (
        ("truncation_observed", truncation_observed)
        if truncation_observed is not None
        else None
    )
    goal: tuple[str, bool] | None = (
        ("goal_attained_observed", goal_attained_observed)
        if goal_attained_observed is not None
        else None
    )

    if not explicit:
        termination = _find_flag(episode_data, TERMINATION_KEYS)
        truncation = _find_flag(episode_data, TRUNCATION_KEYS)
        goal = _find_flag(episode_data, GOAL_KEYS)

    if termination is None and truncation is None and goal is None:
        return _result(
            requirement,
            CheckStatus.UNKNOWN,
            expected=expected,
            actual=None,
            evidence_refs=refs,
            note=(
                "No termination, truncation or goal-attainment evidence is "
                "available; the episode outcome cannot be evaluated"
            ),
            source=source,
        )

    actual_outcome = _classify(termination, truncation, goal)
    observed_signals: dict[str, Any] = {}
    for label, signal in (
        ("termination", termination),
        ("truncation", truncation),
        ("goal", goal),
    ):
        if signal is not None:
            observed_signals[signal[0]] = signal[1]

    # ---- 2. Expectation gate --------------------------------------------
    if expected_outcome is None:
        return _result(
            requirement,
            CheckStatus.UNKNOWN,
            expected=expected,
            actual=actual_outcome,
            evidence_refs=refs,
            note=(
                "No usable expected episode outcome is defined in the "
                "requirement; the observation cannot be evaluated"
            ),
            source=source,
            extra={"observed_signals": observed_signals},
        )

    # ---- 3. Evaluate -----------------------------------------------------
    if actual_outcome is None:
        return _result(
            requirement,
            CheckStatus.UNKNOWN,
            expected=expected,
            actual=None,
            evidence_refs=refs,
            note=(
                "Episode evidence is present but does not determine the "
                "outcome (no positive termination/truncation/goal signal)"
            ),
            source=source,
            extra={"observed_signals": observed_signals},
        )

    # ``terminated`` and ``not_terminated`` describe the same dimension, so a
    # recorded non-terminating episode satisfies an expectation of
    # ``not_terminated`` even though ``_classify`` cannot produce it directly.
    matches = expected_outcome == actual_outcome
    if not matches and expected_outcome == "not_terminated":
        matches = termination is not None and termination[1] is False
    if not matches and expected_outcome == "not_truncated":
        matches = truncation is not None and truncation[1] is False

    note = f"expected={expected_outcome!r}, observed={actual_outcome!r}"

    return _result(
        requirement,
        CheckStatus.PASS if matches else CheckStatus.FAIL,
        expected=expected,
        actual=actual_outcome,
        evidence_refs=refs,
        note=note,
        source=source,
        extra={"observed_signals": observed_signals},
    )


__all__ = ["execute_check"]
