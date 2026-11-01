"""Environment and configuration verification checker.

Compares an explicit requirement against the configuration that is actually
available from the existing system.

Non-negotiable rules (AGENTS.md §4.4):

* A missing configured value or missing expectation is ``UNKNOWN``, never a
  ``FAIL`` and never a fabricated default.
* Non-finite values are reported as ``UNKNOWN`` input rather than compared.
* Only real evidence identifiers are attached to the result.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from backend.verification.models import (
    CheckStatus,
    RequirementType,
    VerificationCheckResult,
    VerificationRequirement,
)

#: Candidate configuration keys per requirement type, in lookup order.
_CONFIG_KEY_CANDIDATES: dict[RequirementType, tuple[str, ...]] = {
    RequirementType.reward: (
        "reward",
        "reward_value",
        "goal_reward",
        "reward_goal",
        "step_reward",
    ),
    RequirementType.termination: (
        "max_episodes",
        "max_steps",
        "termination",
        "termination_condition",
    ),
    RequirementType.metric: ("metric_threshold", "threshold", "metric", "metrics"),
    RequirementType.event: ("event_config", "events", "event"),
    RequirementType.configuration: ("config_value", "value", "config", "setting"),
    RequirementType.observation: (
        "observation_range",
        "observation_space",
        "observation_bounds",
        "observation",
    ),
    RequirementType.action_space: (
        "action_space_bounds",
        "action_space",
        "actions",
    ),
    RequirementType.grid_goal: ("goal_coordinates", "goal_position", "goal", "grid_goal"),
    RequirementType.collision: ("collision_penalty", "collision", "collision_cost"),
}


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _lookup(
    config: dict[str, Any] | None,
    keys: tuple[str, ...],
) -> tuple[str | None, Any]:
    """Return the first present key and its scalar value."""
    if not isinstance(config, dict):
        return None, None
    for key in keys:
        if key in config and _is_scalar(config[key]):
            return key, config[key]
    return None, None


def _comparison_keys(requirement: VerificationRequirement) -> tuple[str, ...]:
    """Resolve the candidate configuration keys for *requirement*."""
    configured_key = requirement.metadata.get("config_key")
    candidates = _CONFIG_KEY_CANDIDATES.get(requirement.type, ())
    if isinstance(configured_key, str) and configured_key:
        return (configured_key, *[key for key in candidates if key != configured_key])
    return candidates


def _result(
    requirement: VerificationRequirement,
    status: CheckStatus,
    *,
    expected: Any,
    actual: Any,
    tolerance: float | None,
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
        tolerance=tolerance,
        evidence_refs=list(evidence_refs or []),
        details=details,
        is_mandatory=requirement.is_mandatory,
    )


def execute_check(
    check_id: str,
    requirement: VerificationRequirement,
    config: dict[str, Any] | None,
    *,
    evidence_refs: list[str] | None = None,
    source: str = "configuration",
) -> VerificationCheckResult:
    """Execute a configuration verification check.

    Args:
        check_id: Identifier for this check (provenance only).
        requirement: The ``VerificationRequirement`` describing the contract.
        config: The actual configuration dict from the environment/system.
        evidence_refs: Real evidence identifiers backing the configuration.
        source: Provenance label recorded in ``details``.

    Returns:
        A ``VerificationCheckResult`` with status ``PASS``, ``FAIL`` or
        ``UNKNOWN``.
    """
    expected = requirement.expected_value
    refs = list(dict.fromkeys(evidence_refs or []))

    if requirement.type not in _CONFIG_KEY_CANDIDATES:
        return _result(
            requirement,
            CheckStatus.UNKNOWN,
            expected=expected,
            actual=None,
            tolerance=None,
            evidence_refs=refs,
            note=f"Unsupported requirement type: {requirement.type!r}",
            source=source,
        )

    key, configured_value = _lookup(config, _comparison_keys(requirement))

    if configured_value is None:
        return _result(
            requirement,
            CheckStatus.UNKNOWN,
            expected=expected,
            actual=None,
            tolerance=None,
            evidence_refs=refs,
            note=(
                "No configured value for this requirement type is available; "
                "the configuration cannot be evaluated"
            ),
            source=source,
            extra={"candidate_keys": list(_comparison_keys(requirement))},
        )

    # The compared configuration entry is the evidence for this check.  It is a
    # location inside the configuration the caller supplied, not a fabricated
    # event or metric identifier, and it keeps a PASS traceable.
    config_ref = f"config.{key}"
    if config_ref not in refs:
        refs.append(config_ref)

    if expected is None:
        return _result(
            requirement,
            CheckStatus.UNKNOWN,
            expected=expected,
            actual=configured_value,
            tolerance=None,
            evidence_refs=refs,
            note="No expected value is defined in the requirement; cannot compare",
            source=source,
            extra={"config_key": key},
        )

    operator = requirement.comparison_operator or "=="
    tolerance = requirement.tolerance
    status, description = _compare(expected, configured_value, operator, tolerance)

    return _result(
        requirement,
        status,
        expected=expected,
        actual=configured_value,
        tolerance=tolerance,
        evidence_refs=refs,
        note=description,
        source=source,
        extra={"config_key": key, "operator": operator},
    )


def _compare(
    expected: Any,
    actual: Any,
    operator: str,
    tolerance: float | None,
) -> tuple[CheckStatus, str]:
    """Compare expected and configured values.

    Numeric values are compared numerically; string/boolean values are
    compared for equality.  Non-comparable combinations return ``UNKNOWN``.
    """
    numeric = (
        isinstance(expected, (int, float))
        and not isinstance(expected, bool)
        and isinstance(actual, (int, float))
        and not isinstance(actual, bool)
    )

    if not numeric:
        if operator in ("==", "!="):
            equal = bool(expected == actual)
            matched = equal if operator == "==" else not equal
            return (
                CheckStatus.PASS if matched else CheckStatus.FAIL,
                f"expected={expected!r}, actual={actual!r}",
            )
        return (
            CheckStatus.UNKNOWN,
            (
                f"Operator {operator!r} is not supported for non-numeric values "
                f"(expected={expected!r}, actual={actual!r})"
            ),
        )

    expected_number = float(expected)
    actual_number = float(actual)

    if not math.isfinite(expected_number) or not math.isfinite(actual_number):
        return (
            CheckStatus.UNKNOWN,
            f"Non-finite value cannot be compared (expected={expected!r}, actual={actual!r})",
        )

    diff = actual_number - expected_number

    if operator == "==":
        if tolerance is not None:
            matched = abs(diff) <= tolerance
            return (
                CheckStatus.PASS if matched else CheckStatus.FAIL,
                f"|actual - expected|={abs(diff):g} vs tolerance={tolerance}",
            )
        matched = diff == 0
        return (
            CheckStatus.PASS if matched else CheckStatus.FAIL,
            f"expected={expected_number:g}, actual={actual_number:g}",
        )
    if operator == "!=":
        matched = diff != 0
        return (
            CheckStatus.PASS if matched else CheckStatus.FAIL,
            f"expected={expected_number:g}, actual={actual_number:g}",
        )
    if operator == ">=":
        threshold = -tolerance if tolerance is not None else 0
        matched = diff >= threshold
        return (
            CheckStatus.PASS if matched else CheckStatus.FAIL,
            f"actual - expected={diff:g} vs threshold={threshold:g}",
        )
    if operator == "<=":
        threshold = tolerance if tolerance is not None else 0
        matched = diff <= threshold
        return (
            CheckStatus.PASS if matched else CheckStatus.FAIL,
            f"actual - expected={diff:g} vs threshold={threshold:g}",
        )
    if operator == ">":
        threshold = tolerance if tolerance is not None else 0
        matched = diff > threshold
        return (
            CheckStatus.PASS if matched else CheckStatus.FAIL,
            f"actual - expected={diff:g} vs threshold={threshold:g}",
        )
    if operator == "<":
        threshold = tolerance if tolerance is not None else 0
        matched = diff < threshold
        return (
            CheckStatus.PASS if matched else CheckStatus.FAIL,
            f"actual - expected={diff:g} vs threshold={threshold:g}",
        )

    return CheckStatus.UNKNOWN, f"Unsupported operator: {operator!r}"


#: Explicit typed alias kept for callers that introspect the extractor table.
Extractor = Callable[[dict[str, Any], str], Any]


__all__ = ["execute_check"]
