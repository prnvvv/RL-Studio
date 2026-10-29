"""Intent validator — validates parsed requirements against the project
contract, rejecting unsupported or ambiguous forms.

Every requirement that reaches the planner/checker pipeline must pass
validation.  Unsupported types, missing expected values, and contradictory
constraints are explicitly flagged.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.verification.models import (
    VerificationRequirement,
    RequirementSource,
    RequirementType,
    CheckStatus,
)


class ValidationError(Dict[str, Any]):
    """A validation error with a type, message, and affected requirement."""
    def __init__(self, req_id: str, message: str, error_type: str = "validation") -> None:
        self.req_id = req_id
        self.message = message
        self.error_type = error_type

    def __repr__(self) -> str:
        return f"ValidationError(req_id={self.req_id!r}, msg={self.message!r}, type={self.error_type!r})"


def validate_requirement(req: VerificationRequirement) -> Tuple[bool, List[ValidationError]]:
    """Validate a single VerificationRequirement against the contract.

    Args:
        req: The requirement to validate.

    Returns:
        (is_valid, errors) where is_valid is True if no contract violations
        were found, and errors is a list of ValidationError objects.
    """
    errors: List[ValidationError] = []

    # 1. Check that the requirement type is supported
    if req.type not in (
        RequirementType.reward,
        RequirementType.termination,
        RequirementType.event,
        RequirementType.metric,
        RequirementType.configuration,
    ):
        errors.append(
            ValidationError(
                req_id=req.id,
                message=f"Unsupported requirement type: {req.type}",
                error_type="unsupported_type",
            )
        )
        return False, errors

    # 2. If the type is reward, expected_value should not be None unless
    #    the intent was explicitly vague (e.g. "the reward should be high").
    #    However, we allow None for "the episode must terminate" type cases.
    if req.type == RequirementType.reward and req.expected_value is None:
        # This is OK if the description makes it clear this is a vagueness case,
        # e.g. "the reward should be high" — but those are handled by the
        # intent parser and will be flagged as unsupported there.
        # For explicit reward equality like "must equal 100", expected_value
        # must be present.
        desc = (req.description or "").lower()
        if "high" in desc or "low" in desc or "good" in desc or "bad" in desc:
            # Vague — will be caught by intent parser unsupported flag
            pass
        else:
            errors.append(
                ValidationError(
                    req_id=req.id,
                    message="Reward requirement has no expected value; expected value required for equality check",
                    error_type="missing_expected_value",
                )
            )

    # 3. Event requirements: if type is event and no forbidden/required
    #    specification is present, that's OK — the workflow planner will
    #    dispatch the check and the checker handles it.
    #    We only validate here that the type is supported.

    # 4. Metric requirements: if expected_value is None and no operator
    #    can be applied, flag it.
    if req.type == RequirementType.metric and req.expected_value is None:
        errors.append(
            ValidationError(
                req_id=req.id,
                message="Metric requirement has no expected value; a threshold must be specified",
                error_type="missing_expected_value",
            )
        )

    # 5. Check for contradictory operators (e.g. both == and != on the same
    #    requirement — not possible with our model, but we guard against
    #    nonsensical combinations).
    if req.comparison_operator not in (
        "==",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        None,
    ):
        errors.append(
            ValidationError(
                req_id=req.id,
                message=f"Invalid comparison operator: {req.comparison_operator}",
                error_type="invalid_operator",
            )
        )

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_requirements(requirements: List[VerificationRequirement]) -> Dict[str, Any]:
    """Validate a list of requirements and return a summary.

    Args:
        requirements: List of VerificationRequirement to validate.

    Returns:
        Dict with:
        - "valid": number of valid requirements
        - "invalid": number of invalid requirements
        - "errors": dict mapping requirement ID to list of ValidationError
    """
    summary: Dict[str, Any] = {
        "valid": 0,
        "invalid": 0,
        "errors": {},
    }

    for req in requirements:
        is_valid, errors = validate_requirement(req)
        summary["total"] = summary.get("total", 0) + 1  # type: ignore[attr-defined]
        if is_valid:
            summary["valid"] += 1
        else:
            summary["invalid"] += 1
            summary["errors"][req.id] = [
                {"message": e.message, "type": e.error_type} for e in errors
            ]

    return summary