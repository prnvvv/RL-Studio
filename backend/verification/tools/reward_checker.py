"""Reward requirement verification checker.

Distinguishes between configured reward values and observed runtime rewards.

See ``backend/verification/tools/`` for the package README and integration notes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.verification.models import (
    VerificationCheckResult,
    VerificationRequirement,
)


def _extract_reward_value(
    source: Optional[Dict[str, Any]],
    key: str = "reward",
) -> Optional[float]:
    """Extract a numeric reward value from a dict-like source.

    Returns None if the key is absent, the value is not numeric, or source is
    None.
    """
    if source is None:
        return None
    val = source.get(key)
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _extract_episode_return(
    source: Optional[Dict[str, Any]],
    key: str = "episode_return",
) -> Optional[float]:
    """Extract an episode return (accumulated reward) from a dict-like source.

    Returns None if the key is absent or the value is not numeric.
    """
    if source is None:
        return None
    val = source.get(key)
    if isinstance(val, (int, float)):
        return float(val)
    return None


def _make_details(note: str, source: Optional[str] = None) -> Dict[str, Any]:
    """Create a details dict compatible with VerificationCheckResult."""
    d: Dict[str, Any] = {"note": note}
    if source is not None:
        d["source"] = source
    return d


def execute_check(
    check_id: str,
    requirement: VerificationRequirement,
    *,
    configured_reward: Optional[float] = None,
    observed_reward: Optional[float] = None,
    episode_data: Optional[Dict[str, Any]] = None,
    source: str = "reward_check",
) -> VerificationCheckResult:
    """Execute a reward requirement verification check.

    Distinguishes between configured reward values and observed runtime rewards.

    Only the checks supported by actual available evidence are implemented.

    Args:
        check_id: Identifier for this check.
        requirement: The ``VerificationRequirement`` describing what is expected.
        configured_reward: The reward value configured in the environment, if
            available.
        observed_reward: The reward observed during execution, if available.
        episode_data: Optional episode-level data that may contain reward
            information.
        source: Human-readable source label for evidence provenance.

    Returns:
        A ``VerificationCheckResult`` with status ``PASS``, ``FAIL``,
        ``UNKNOWN``, or ``ERROR``.
    """
    expected = requirement.expected_value
    actual = None
    evidence_parts: List[str] = []

    # Determine what evidence is available and what to compare
    # Critical: if there is no observed reward (from actual execution evidence),
    # we must NOT fabricate or default to the configured value.  Return UNKNOWN.
    if observed_reward is None:
        # No actual observed reward — cannot compare; return UNKNOWN
        from backend.verification.models import VerificationCheckResult

        return VerificationCheckResult(
            requirement_id=requirement.id,
            status="unknown",
            expected=expected,
            actual=None,
            tolerance=None,
            evidence_refs=[],
            details={"note": "No observed reward available from execution evidence; cannot compare", "source": source},
        )

    if configured_reward is None:
        # Only observed reward available; use it as actual
        actual = observed_reward
        evidence_parts.append("observed_reward")
    elif observed_reward is not None and configured_reward is not None:
        # Both available — compare them
        actual = observed_reward
        evidence_parts.extend(["configured_reward", "observed_reward"])
    else:
        # Should not reach here (observed_reward is not None handled above),
        # but be safe.
        from backend.verification.models import VerificationCheckResult

        return VerificationCheckResult(
            requirement_id=requirement.id,
            status="unknown",
            expected=expected,
            actual=None,
            tolerance=None,
            evidence_refs=[],
            details={"note": "Unexpected evidence state", "source": source},
        )

    expected_num = float(expected) if expected is not None else None
    actual_num = float(actual) if actual is not None else None

    if expected_num is None:
        from backend.verification.models import VerificationCheckResult

        return VerificationCheckResult(
            requirement_id=requirement.id,
            status="unknown",
            expected=expected,
            actual=actual,
            tolerance=None,
            evidence_refs=[],
            details={"note": "Expected reward value is null; cannot compare", "source": source},
        )

    # Use the requirement's comparison operator and tolerance
    operator = requirement.comparison_operator or "=="
    tolerance = requirement.tolerance

    # Perform comparison
    try:
        comparison_result = _compare_reward_numeric(
            expected_num, actual_num, operator, tolerance
        )

        from backend.verification.models import VerificationCheckResult

        details = {"msg": comparison_result["msg"], "source": source}

        result = VerificationCheckResult(
            requirement_id=requirement.id,
            status=comparison_result["status"],
            expected=expected,
            actual=actual,
            tolerance=tolerance,
            evidence_refs=[],
            details=details,
        )

        # Add evidence references if we have them
        if evidence_parts:
            result.evidence_refs.extend(
                [f"reward_source:{p}" for p in evidence_parts]
            )

        return result

    except (ValueError, TypeError) as exc:
        from backend.verification.models import VerificationCheckResult

        return VerificationCheckResult(
            requirement_id=requirement.id,
            status="error",
            expected=expected,
            actual=actual,
            tolerance=tolerance,
            evidence_refs=[],
            details={"msg": f"Comparison error: {exc}", "source": source},
        )


def _compare_reward_numeric(
    expected: float,
    actual: float,
    operator: str,
    tolerance: Optional[float],
) -> Dict[str, str]:
    """Compare two numeric reward values using the given operator and tolerance.

    Returns a dict with ``status`` and ``msg`` (a plain string, compatible with
    the ``details`` field of ``VerificationCheckResult`` after adding ``source``).
    """
    diff = actual - expected

    if operator == "==":
        if tolerance is not None:
            if abs(diff) <= tolerance:
                return {"status": "pass", "msg": f"|actual - expected|={abs(diff):.2f} <= tolerance={tolerance}"}
            return {"status": "fail", "msg": f"|actual - expected|={abs(diff):.2f} > tolerance={tolerance}"}
        if diff == 0:
            return {"status": "pass", "msg": "exact match"}
        return {"status": "fail", "msg": f"expected={expected}, actual={actual}"}

    elif operator == ">=":
        threshold = -tolerance if tolerance is not None else 0
        if diff >= threshold:
            return {"status": "pass", "msg": f"actual - expected >= {threshold}"}
        return {"status": "fail", "msg": f"actual - expected < {threshold}"}

    elif operator == "<=":
        threshold = tolerance if tolerance is not None else 0
        if diff <= threshold:
            return {"status": "pass", "msg": f"actual - expected <= {threshold}"}
        return {"status": "fail", "msg": f"actual - expected > {threshold}"}

    elif operator == ">":
        threshold = tolerance if tolerance is not None else 0
        if diff > threshold:
            return {"status": "pass", "msg": f"actual - expected > {threshold}"}
        return {"status": "fail", "msg": f"actual - expected <= {threshold}"}

    elif operator == "<":
        threshold = tolerance if tolerance is not None else 0
        if diff < threshold:
            return {"status": "pass", "msg": f"actual - expected < {threshold}"}
        return {"status": "fail", "msg": f"actual - expected >= {threshold}"}

    elif operator == "!=":
        if diff != 0:
            return {"status": "pass", "msg": "values differ"}
        return {"status": "fail", "msg": "values are equal"}

    else:
        return {"status": "unknown", "msg": f"Unsupported operator: {operator!r}"}


# ---------------------------------------------------------------------------
# Module initialisation: no side effects beyond function definitions.
# ---------------------------------------------------------------------------

# Ensure the module can be imported without side effects beyond function
# definitions and the harmless helper functions above.  No API calls, no
# network hooks, no registry mutations occur at module load time.