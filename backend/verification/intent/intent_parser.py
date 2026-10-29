"""Intent parser — interprets natural-language developer intent into structured
requirements, preserving the original text and extracting supported constraints.

Deterministic only — no LLM calls.  Unsupported or ambiguous intents return
explicit errors rather than inventing thresholds.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from backend.verification.models import RequirementSource, RequirementType


class ParsedIntent(Dict[str, Any]):
    """Structured output of intent parsing.

    Holds all requirements that could be deterministically extracted,
    with their types, expected values, operators, and source text.
    """

    def __init__(self) -> None:
        self.requirements: List[Dict[str, Any]] = []
        self.original_text: str = ""
        self.ambiguity_reason: Optional[str] = None
        self.unsupported: bool = False


def parse_intent(text: str) -> ParsedIntent:
    """Parse a natural-language intent string into structured requirements.

    Supported forms (deterministic, regex-guided):
      - "The goal reward must equal 100."
      - "The goal reward must be at least 100."
      - "The episode must finish within 200 steps."
      - "The goal reward must equal 25 and the episode must finish within 200 steps."
      - "The episode must terminate successfully."
      - "The agent must never emit the forbidden event."
      - "The learning rate must remain at 0.001."

    Unsupported/ambiguous forms will set ``unsupported=True`` or
    ``ambiguity_reason`` rather than silently inventing constraints.
    """
    result = ParsedIntent()
    result["original_text"] = text
    result["unsupported"] = False
    result["ambiguity_reason"] = None
    result["requirements"] = []

    if not text or not text.strip():
        result["ambiguity_reason"] = "empty intent"
        result["unsupported"] = True
        return result

    text_lower = text.lower().strip()

    # ------------------------------------------------------------------
    # 1. Parse independent requirements using keyword + numeric extraction.
    #    Each requirement is extracted separately so multiple constraints
    #    in one sentence remain distinct.
    # ------------------------------------------------------------------

    # --- Reward equality/inequality ---
    reward_req = _parse_reward_requirement(text)
    if reward_req is not None:
        result["requirements"].append(reward_req)

    # --- Step/episode count ---
    step_req = _parse_step_requirement(text)
    if step_req is not None:
        result["requirements"].append(step_req)

    # --- Termination ---
    term_req = _parse_termination_requirement(text)
    if term_req is not None:
        result["requirements"].append(term_req)

    # --- Event ---
    event_req = _parse_event_requirement(text)
    if event_req is not None:
        result["requirements"].append(event_req)

    # --- Metric/threshold ---
    metric_req = _parse_metric_requirement(text)
    if metric_req is not None:
        result["requirements"].append(metric_req)

    # --- Learning rate ---
    lr_req = _parse_learning_rate_requirement(text)
    if lr_req is not None:
        result["requirements"].append(lr_req)

    # ------------------------------------------------------------------
    # 2. Detect ambiguity / unsupported forms.
    #    If we found no deterministic constraints but the text is
    #    clearly trying to express something, flag it.
    # ------------------------------------------------------------------
    if not result["requirements"] and not result["unsupported"]:
        # Heuristic: if the text contains vaguely evaluative language
        # without a concrete numerical threshold, flag ambiguity.
        vaguephrases = ["high", "low", "good", "bad", "efficient", "stable"]
        has_vague = any(p in text_lower for p in vaguephrases)
        if has_vague:
            result["ambiguity_reason"] = (
                "vague evaluative language without a concrete threshold; "
                "cannot extract a testable requirement"
            )
            result["unsupported"] = True
        # If the text is just a statement without recognizable structure,
        # leave it unsupported rather than inventing a requirement.

    return result


# ----------------------------------------------------------------------
# Parsers for each requirement type
# ----------------------------------------------------------------------


def _extract_number(text: str) -> Optional[float]:
    """Extract the first numeric constant from *text*.

    Returns None if no number can be found.
    """
    numbers = re.findall(r"-?\d+(?:\.\d+)?", text)
    if not numbers:
        return None
    try:
        return float(numbers[0])
    except ValueError:
        return None


def _parse_reward_requirement(text: str) -> Optional[Dict[str, Any]]:
    """Parse ``goal reward must equal X`` or ``must be at least X`` etc.

    Returns a dict suitable for a VerificationRequirement, or None.
    """
    text_lower = text.lower()

    # Pattern: "reward must equal X" / "reward must be at least X" etc.
    patterns = [
        (r"reward must\s+equal\s+([\d.]+)", "=="),
        (r"reward must\s+be\s+at\s+least\s+([\d.]+)", ">="),
        (r"reward must\s+be\s+at most\s+([\d.]+)", "<="),
        (r"reward must\s+be\s+greater\s+than\s+([\d.]+)", ">"),
        (r"reward must\s+be\s+less\s+than\s+([\d.]+)", "<"),
        (r"goal reward must\s+equal\s+([\d.]+)", "=="),
        (r"goal reward must\s+be\s+at least\s+([\d.]+)", ">="),
        (r"goal reward must\s+be\s+at most\s+([\d.]+)", "<="),
    ]

    for pattern, operator in patterns:
        m = re.search(pattern, text_lower)
        if m:
            value = float(m.group(1))
            return {
                "type": RequirementType.reward.value,
                "expected_value": value,
                "comparison_operator": operator,
                "description": f"goal reward {operator} {value}",
                "source": RequirementSource.code_inferred.value,
            }

    return None


def _parse_step_requirement(text: str) -> Optional[Dict[str, Any]]:
    """Parse ``episode must finish within X steps`` or similar."""
    text_lower = text.lower()

    patterns = [
        (r"episode must finish within\s+(\d+)\s+steps?", "=="),
        (r"within\s+(\d+)\s+steps?", "=="),
        (r"max steps?\s*[:=]\s*(\d+)", "=="),
    ]

    for pattern, operator in patterns:
        m = re.search(pattern, text_lower)
        if m:
            steps = int(m.group(1))
            return {
                "type": RequirementType.termination.value,
                "expected_value": steps,
                "comparison_operator": operator,
                "description": f"episode within {steps} steps {operator}",
                "source": RequirementSource.code_inferred.value,
            }

    return None


def _parse_termination_requirement(text: str) -> Optional[Dict[str, Any]]:
    """Parse ``episode must terminate successfully`` etc."""
    text_lower = text.lower()

    if "terminate successfully" in text_lower or "terminate success" in text_lower:
        return {
            "type": RequirementType.termination.value,
            "expected_value": True,
            "comparison_operator": "==",
            "description": "episode terminate successfully",
            "source": RequirementSource.code_inferred.value,
        }

    if "terminate" in text_lower and "success" not in text_lower:
        # "the episode must terminate" without qualification → we can
        # record that termination is expected but not specify a Boolean
        # value; return expected_value=None so the checker handles it.
        return {
            "type": RequirementType.termination.value,
            "expected_value": None,
            "comparison_operator": "==",
            "description": "episode must terminate",
            "source": RequirementSource.code_inferred.value,
        }

    return None


def _parse_event_requirement(text: str) -> Optional[Dict[str, Any]]:
    """Parse ``agent must never emit the forbidden event`` etc."""
    text_lower = text.lower()

    if "never emit" in text_lower or "forbidden event" in text_lower:
        return {
            "type": RequirementType.event.value,
            "expected_value": None,
            "comparison_operator": "!=",  # "never" → event must not occur
            "description": "agent must never emit forbidden event",
            "source": RequirementSource.code_inferred.value,
        }

    if "must emit the goal reached event" in text_lower or "must emit goal_reached" in text_lower:
        return {
            "type": RequirementType.event.value,
            "expected_value": None,
            "comparison_operator": "==",
            "description": "agent must emit goal_reached event",
            "source": RequirementSource.code_inferred.value,
        }

    return None


def _parse_metric_requirement(text: str) -> Optional[Dict[str, Any]]:
    """Parse ``reward should be high`` etc. — intentionally vague."""
    # We do not invent a threshold for "high"; return None and let the
    # caller flag ambiguity.
    return None


def _parse_learning_rate_requirement(text: str) -> Optional[Dict[str, Any]]:
    """Parse ``learning rate must remain at 0.001`` etc."""
    text_lower = text.lower()

    m = re.search(r"learning rate must remain at\s+([\d.]+?)(?:\s|$)", text_lower)
    if m:
        lr_str = m.group(1).rstrip(".")
        try:
            lr = float(lr_str)
        except ValueError:
            return None
        return {
            "type": RequirementType.configuration.value,
            "expected_value": lr,
            "comparison_operator": "==",
            "description": f"learning rate == {lr}",
            "source": RequirementSource.code_inferred.value,
        }

    # Also handle "learning rate should be X"
    m2 = re.search(r"learning rate should be\s+([\d.]+)", text_lower)
    if m2:
        lr = float(m2.group(1))
        return {
            "type": RequirementType.configuration.value,
            "expected_value": lr,
            "comparison_operator": "==",
            "description": f"learning rate == {lr}",
            "source": RequirementSource.code_inferred.value,
        }

    return None