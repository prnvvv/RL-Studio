"""Reward requirement verification checker.

Compares an explicit, developer-confirmed expected reward against a reward that
was **actually observed** during execution.

Non-negotiable rules (AGENTS.md §7.3, §13):

* A missing observation is ``UNKNOWN``/``not_evaluable`` — never a fabricated
  ``0.0`` and never a PASS.
* A missing expectation is ``UNKNOWN`` — never inferred from the observation.
* Only real evidence identifiers are attached to the result.
* Low reward alone is not an environment defect.
"""

from __future__ import annotations

import math
from typing import Any

from backend.verification.models import (
    CheckStatus,
    VerificationCheckResult,
    VerificationRequirement,
)


def _finite_reward(value: float | None) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _result(
    requirement: VerificationRequirement,
    status: CheckStatus,
    *,
    expected: Any = None,
    actual: Any = None,
    tolerance: float | None = None,
    evidence_refs: list[str] | None = None,
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
    *,
    configured_reward: float | None = None,
    observed_reward: float | None = None,
    evidence_refs: list[str] | None = None,
    source: str = "reward_check",
) -> VerificationCheckResult:
    """Execute a reward requirement verification check.

    Args:
        check_id: Identifier for this check (provenance only).
        requirement: The requirement describing the confirmed contract.
        configured_reward: The reward value configured in the environment, if
            supplied as evidence.
        observed_reward: The reward value actually observed at runtime, if
            supplied as evidence.  ``None`` means "not observed".
        evidence_refs: Real evidence identifiers backing the observation.
        source: Provenance label recorded in ``details``.

    Returns:
        A ``VerificationCheckResult`` with status ``PASS``, ``FAIL``,
        ``UNKNOWN`` or ``ERROR``.
    """
    expected = requirement.expected_value

    # ---- 1. Observation gate ---------------------------------------------
    observed_num = _finite_reward(observed_reward)
    if observed_num is None:
        note = (
            "No usable observed reward available from execution evidence; "
            "cannot compare"
            if observed_reward is None
            else "Observed reward is not a finite number; cannot compare"
        )
        return _result(
            requirement,
            CheckStatus.UNKNOWN,
            expected=expected,
            actual=None,
            note=note,
            source=source,
        )

    # ---- 2. Expectation gate ---------------------------------------------
    expected_num = _finite_reward(expected)
    if expected_num is None:
        note = (
            "No confirmed expected reward value; cannot evaluate the observation"
            if expected is None
            else "Expected reward is not a finite number; cannot compare"
        )
        return _result(
            requirement,
            CheckStatus.UNKNOWN,
            expected=expected,
            actual=observed_reward,
            evidence_refs=evidence_refs,
            note=note,
            source=source,
        )

    # ---- 3. Evaluate -----------------------------------------------------
    operator = requirement.comparison_operator or "=="
    tolerance = requirement.tolerance
    comparison = _compare_reward_numeric(expected_num, observed_num, operator, tolerance)

    status = {
        "pass": CheckStatus.PASS,
        "fail": CheckStatus.FAIL,
        "unknown": CheckStatus.UNKNOWN,
    }[comparison["status"]]

    extra: dict[str, Any] = {}
    if configured_reward is not None:
        configured_num = _finite_reward(configured_reward)
        extra["configured_reward"] = configured_num
        if configured_num is not None and configured_num != expected_num:
            extra["configured_reward_differs_from_requirement"] = True

    return _result(
        requirement,
        status,
        expected=expected,
        actual=observed_reward,
        tolerance=tolerance,
        evidence_refs=evidence_refs,
        note=comparison["msg"],
        source=source,
        extra=extra,
    )


def _compare_reward_numeric(
    expected: float,
    actual: float,
    operator: str,
    tolerance: float | None,
) -> dict[str, str]:
    """Compare two finite numeric reward values.

    Returns ``{"status": "pass"|"fail"|"unknown", "msg": str}``.
    """
    diff = actual - expected

    if operator == "==":
        if tolerance is not None:
            if abs(diff) <= tolerance:
                return {
                    "status": "pass",
                    "msg": f"|actual - expected|={abs(diff):.4f} <= tolerance={tolerance}",
                }
            return {
                "status": "fail",
                "msg": f"|actual - expected|={abs(diff):.4f} > tolerance={tolerance}",
            }
        if diff == 0:
            return {"status": "pass", "msg": "exact match"}
        return {"status": "fail", "msg": f"expected={expected}, actual={actual}"}

    if operator == ">=":
        if diff >= 0:
            return {"status": "pass", "msg": "actual >= expected"}
        return {"status": "fail", "msg": f"actual < expected (diff={diff:g})"}

    if operator == "<=":
        if diff <= 0:
            return {"status": "pass", "msg": "actual <= expected"}
        return {"status": "fail", "msg": f"actual > expected (diff={diff:g})"}

    if operator == ">":
        if diff > 0:
            return {"status": "pass", "msg": "actual > expected"}
        return {"status": "fail", "msg": f"actual <= expected (diff={diff:g})"}

    if operator == "<":
        if diff < 0:
            return {"status": "pass", "msg": "actual < expected"}
        return {"status": "fail", "msg": f"actual >= expected (diff={diff:g})"}

    if operator == "!=":
        if diff != 0:
            return {"status": "pass", "msg": "values differ"}
        return {"status": "fail", "msg": "values are equal"}

    return {"status": "unknown", "msg": f"Unsupported operator: {operator!r}"}


__all__ = ["execute_check"]
