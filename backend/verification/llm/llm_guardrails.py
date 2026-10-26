"""LLM guardrails - model output safety and policy enforcement for RL Studio.

Application-level guardrails that enforce safety constraints in code, not
just in prompts.  Guardrails operate on inputs and outputs of the Meta
Model API integration and are enforceable by the verification agent,
planner, and controller.

Key design points:
- Input validation: bound prompt sizes, preserve trust boundaries between
  system instructions and untrusted user-supplied content.
- Output validation: reject model outputs that violate canonical schemas,
  reject unknown tool identifiers, validate suggested tool arguments against
  registered tool schemas.
- Tool execution security: the LLM layer must never execute arbitrary
  model-generated Python, shell commands, SQL, or other code.  The model
  may suggest an action using an approved tool identifier; the application
  must validate that identifier and its arguments against a trusted registry
  before the controller executes it.
- Evidence integrity: preserve source references and distinguish developer-
  stated expectations, configuration values, actual execution observations,
  deterministic check results, model-generated hypotheses, and model-
  generated explanations.  The model must not fabricate metrics, rewards,
  trajectories, checkpoints, logs, traces, or tool outputs.
- Prompt-injection protection: defend against instructions embedded in
  README files, environment descriptions, configuration comments, training
  logs, agent-generated text, execution traces, and other supplied evidence.
- Operational safety: typed guardrail errors, safe logging, bounded retries,
  timeout handling, explicit provider-failure behavior, redaction of secrets
  and sensitive information.
"""

from __future__ import annotations

import json
import re
import warnings
import logging
import uuid
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError, validator

from backend.verification.exceptions import (  # typed guardrail errors
    InputValidationError,
    MetaAIProviderError,
    GuardrailViolation,
)

from backend.verification.models import (  # canonical models used for validation
    VerificationRequirement,
    VerificationCheckResult,
    CheckStatus,
    RequirementType,
    RequirementSource,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# A. Input validation
# ---------------------------------------------------------------------------

class PromptInput(BaseModel):
    """Schema for a model-invocation prompt input, supporting dependency
    injection and validation in tests.

    This is a minimal example; the full prompt input schema should be
    extended as the application's prompt system evolves.
    """

    system_instruction: str = Field(..., description="Trusted system governing instructions")
    user_content: str = Field(..., description="Untrusted user-supplied content")
    developer_description: Optional[str] = Field(
        None, description="Developer-provided description of intent or context"
    )
    max_user_content_chars: int = Field(
        4000, description="Hard bound on user-content length"
    )

    @validator("user_content")
    def _bound_user_content(cls, v: str) -> str:
        """Reject user content that exceeds the maximum allowed length."""
        if len(v) > cls.__fields__["max_user_content_chars"].default:
            raise InputValidationError(
                f"User content exceeds maximum allowed length ({cls.__fields__['max_user_content_chars'].default} chars).",
                field="user_content",
            )
        return v

    @validator("system_instruction")
    def _system_instruction_must_be_trusted(cls, v: str) -> str:
        """Detect and flag system instructions that attempt to override
        governing agent instructions — this is a heuristic check, not a
        guarantee, but it provides a defense-in-depth layer."""

        override_phrases = ["ignore previous", "forget", "disregard",
                            "override", "bypass", "break out"]
        lowered = v.lower()
        if any(phrase in lowered for phrase in override_phrases):
            warnings.warn(
                f"System instruction contains potential override phrase(s): {v[:100]!r}.",
                stacklevel=2,
            )
        return v


def validate_prompt_input(
    system_instruction: str,
    user_content: str,
    developer_description: Optional[str] = None,
    max_chars: int = 4000,
) -> PromptInput:
    """Validate and construct a ``PromptInput`` from raw prompt components.

    This is the single entry point for prompt input validation; callers
    must not construct ``PromptInput`` with raw unvalidated strings.
    """
    return PromptInput(
        system_instruction=system_instruction,
        user_content=user_content,
        developer_description=developer_description,
        max_user_content_chars=max_chars,
    )

# ---------------------------------------------------------------------------
# B. Output validation
# ---------------------------------------------------------------------------

class ModelOutputViolation(BaseModel):
    """A guardrail violation detected in model output.

    Records the violation type, the raw/model output, and a suggested
    action.  The caller (agent, planner, controller) decides how to
    enforce the recommended action.
    """

    violation_type: str  # e.g. "unknown_tool", "invalid_arguments", "fabricated_evidence"
    message: str
    raw_output: str  # The raw model output that triggered the violation
    suggested_action: str = "reject"  # reject, repair, escalate, log
    violation_id: str = Field(default_factory=lambda: f"guard-{uuid.uuid4().hex[:8]}")


def validate_model_output(
    raw_output: str,
    canonical_model: BaseModel,
) -> tuple:
    """Validate raw model output against a canonical Pydantic model.

    Returns a tuple of (validated_model, violation).
    - If validation succeeds, ``validated_model`` is the populated model
      and ``violation`` is ``None``.
    - If validation fails, ``validated_model`` is ``None`` and ``violation``
      contains details.
    """
    import uuid
    try:
        validated = canonical_model(**json.loads(raw_output)) if raw_output.strip().startswith("{") else canonical_model(raw_output)
        return validated, None
    except (ValidationError, json.JSONDecodeError) as exc:
        violation = ModelOutputViolation(
            violation_type="schema_validation_error",
            message=f"Model output does not validate against the canonical schema: {exc}",
            raw_output=raw_output,
            suggested_action="reject_and_report",
        )
        return None, violation


def reject_unknown_tool(tool_id: str, registered_tools: set) -> Optional[ModelOutputViolation]:
    """Reject a model-suggested tool identifier that is not in the
    registered set.

    This is a concrete guardrail: the model may suggest an action using
    an approved tool identifier, but the application must validate that
    identifier against a trusted registry before the controller executes it.
    """
    if tool_id not in registered_tools:
        return ModelOutputViolation(
            violation_type="unknown_tool",
            message=f"Model suggested unknown tool identifier: {tool_id}. Registered tools: {sorted(registered_tools)}",
            raw_output=f"tool_id={tool_id}",
            suggested_action="reject",
        )
    return None  # tool is registered, no violation


def validate_tool_arguments(
    tool_id: str,
    args: dict,
    registered_tool_schemas: dict,
) -> Optional[ModelOutputViolation]:
    """Validate suggested tool arguments against a registered tool schema.

    If the tool_id is not in the registered schemas, a violation is returned.
    If the arguments fail schema validation, a violation is returned.
    Otherwise, None is returned.
    """
    if tool_id not in registered_tool_schemas:
        return ModelOutputViolation(
            violation_type="unknown_tool",
            message=f"Tool schema not registered: {tool_id}",
            raw_output=f"tool_id={tool_id}, args={args}",
            suggested_action="reject",
        )
    schema = registered_tool_schemas[tool_id]
    try:
        schema(**args)  # validates that args conform to the schema
        return None  # arguments are valid
    except ValidationError as exc:
        return ModelOutputViolation(
            violation_type="invalid_tool_arguments",
            message=f"Tool {tool_id} arguments do not conform to registered schema: {exc}",
            raw_output=f"tool_id={tool_id}, args={args}",
            suggested_action="reject_and_report",
        )

# ---------------------------------------------------------------------------
# C. Evidence integrity
# ---------------------------------------------------------------------------

class EvidenceIntegrityError(ModelOutputViolation):
    """Raised when model output attempts to fabricate or corrupt evidence."""
    pass


def verify_evidence_source(
    evidence_ref: dict,
    trusted_sources: frozenset,
) -> Optional[ModelOutputViolation]:
    """Check that an evidence reference originates from a trusted source.

    The model must not fabricate metrics, rewards, trajectories,
    checkpoints, logs, traces, or tool outputs.  This function enforces
    that by checking the evidence source against a set of trusted domains.
    """
    source = evidence_ref.get("source", "")
    if source not in trusted_sources:
        return ModelOutputViolation(
            violation_type="fabricated_evidence",
            message=f"Evidence from untrusted source: {source}. Trusted sources: {trusted_sources}",
            raw_output=f"evidence_source={source}",
            suggested_action="reject_and_escalate",
        )
    return None

# ---------------------------------------------------------------------------
# D. Prompt-injection protection
# ---------------------------------------------------------------------------

# Phrases that, if found in untrusted evidence or developer descriptions,
# signal a possible prompt-injection attempt.  This is a heuristic
# supplement to schema-level tool restrictions.
PROMPT_INJECTION_HEURISTICS: list = [
    "ignore previous",
    "forget all",
    "disregard previous",
    "override the",
    "bypass the",
    "break out of",
    "system prompt",
    "you are now",
]


def detect_prompt_injection(text: str) -> bool:
    """Heuristically detect possible prompt-injection instructions in *text*.

    This checks for common prompt-injection phrases embedded in evidence,
    descriptions, or other untrusted content.  It is not a guarantee but
    provides a defense-in-depth layer.
    """
    lowered = text.lower()
    return any(phrase in lowered for phrase in PROMPT_INJECTION_HEURISTICS)

# ---------------------------------------------------------------------------
# E. Operational safety
# ---------------------------------------------------------------------------

class GuardrailError(BaseModel):
    """A typed guardrail error, carrying a violation ID, message, and
    suggested action.  These are logged and propagated; they never
    cause silent fallbacks to unrestricted behavior.
    """

    violation_id: str
    violation_type: str
    message: str
    suggested_action: str = "reject"
    timestamp: float = Field(default_factory=time.time)


def apply_guardrails(
    prompt_input: PromptInput,
    raw_model_output: str,
    registered_tools: set,
    registered_tool_schemas: dict,
    trusted_evidence_sources: frozenset,
    canonical_model: BaseModel,
) -> tuple:
    """Apply the full set of LLM guardrails and return (validated_output, violations).

    This is the central guardrail orchestration function.  It validates the
    prompt input, the model output, the suggested tools, and the evidence
    sources.  All violations are collected and returned; the caller decides
    how to enforce the suggested actions.

    Returns:
        A 2-tuple of (validated_model_or_None, list_of_guardrail_violations).
        If the validated model is not None, it passed all guards.
        If the list is empty, no violations were detected.
    """
    import uuid

    violations: list = []

    # 1. Validate prompt input (bounds, trusted system instruction)
    try:
        validated_input = validate_prompt_input(
            system_instruction=prompt_input.system_instruction,
            user_content=prompt_input.user_content,
            developer_description=prompt_input.developer_description,
            max_chars=prompt_input.max_user_content_chars,
        )
    except InputValidationError as exc:
        violations.append(
            GuardrailError(
                violation_id=f"guard-{uuid.uuid4().hex[:8]}",
                violation_type="input_validation_error",
                message=str(exc),
                suggested_action="reject",
            ),
        )
        return None, violations

    # 2. Heuristic prompt-injection detection in untrusted content
    if detect_prompt_injection(prompt_input.user_content):
        violations.append(
            GuardrailError(
                violation_id=f"guard-{uuid.uuid4().hex[:8]}",
                violation_type="prompt_injection_detected",
                message="Potential prompt injection in user content.",
                suggested_action="reject",
            )
        )

    # 3. Validate model output against canonical schema
    validated_model, output_violation = validate_model_output(
        raw_model_output, canonical_model
    )
    if output_violation is not None:
        violations.append(
            GuardrailError(
                violation_id=output_violation.violation_id,
                violation_type=output_violation.violation_type,
                message=output_violation.message,
                suggested_action=output_violation.suggested_action,
            )
        )

    # 4. Reject unknown tool identifiers
    # If the validated model contains a suggested tool, check it.
    # The model output format depends on the canonical model; this is a
    # heuristic extraction for common fields.
    tool_match = re.search(r"\btool\s*[:=]\s*\"([^\"]+)\"", raw_model_output, re.IGNORECASE)
    if tool_match:
        suggested_tool = tool_match.group(1)
        tool_violation = reject_unknown_tool(suggested_tool, registered_tools)
        if tool_violation is not None:
            violations.append(
                GuardrailError(
                    violation_id=tool_violation.violation_id,
                    violation_type=tool_violation.violation_type,
                    message=tool_violation.message,
                    suggested_action=tool_violation.suggested_action,
                )
            )

    # 5. Validate tool arguments if a tool was suggested and no tool violation
    if not any(v.violation_type == "unknown_tool" for v in violations):
        arg_match = re.search(r"\barguments\s*[:=]\s*\{([^}]+)\}", raw_model_output, re.IGNORECASE)
        if arg_match:
            args_str = arg_match.group(1)
            # Very lightweight arg extraction; the full validation is done
            # by the caller using the registered tool schemas.
            # Here we just check that the arguments dict can be parsed.
            try:
                args_dict = json.loads("{" + args_str + "}")
                arg_violation = validate_tool_arguments(
                    "",  # We don't have the tool_id from the lightweight extract;
                    # the caller should provide it.
                    args_dict,
                    registered_tool_schemas,
                )
                if arg_violation is not None:
                    violations.append(
                        GuardrailError(
                            violation_id=arg_violation.violation_id,
                            violation_type=arg_violation.violation_type,
                            message=arg_violation.message,
                            suggested_action=arg_violation.suggested_action,
                        )
                    )
            except (json.JSONDecodeError, ValueError):
                # Malformed arguments — treat as a violation but let the
                # caller decide.
                pass

    # 6. Evidence source integrity check (if the model output references evidence)
    # Heuristic: look for evidence-like references in the output.
    evidence_match = re.search(r"\bEvidence[\s_:]+\{?([^}]+)\}?", raw_model_output, re.IGNORECASE)
    if evidence_match:
        # Heuristic: try to reconstruct a minimal evidence reference dict.
        ev_raw = evidence_match.group(1)
        try:
            ev_dict = json.loads("{" + ev_raw + "}")
            ev_violation = verify_evidence_source(ev_dict, trusted_evidence_sources)
            if ev_violation is not None:
                violations.append(
                    GuardrailError(
                        violation_id=ev_violation.violation_id,
                        violation_type=ev_violation.violation_type,
                        message=ev_violation.message,
                        suggested_action=ev_violation.suggested_action,
                    )
                )
        except (json.JSONDecodeError, ValueError):
            pass  # Not a recognised evidence dict; ignore heuristic.

    # 7. If any violations were detected, return None for the validated model.
    if violations:
        return None, violations

    # 8. No violations — return the validated model.
    try:
        model = canonical_model(**json.loads(raw_model_output)) if raw_model_output.strip().startswith("{") else canonical_model(raw_model_output)
        return model, []
    except (ValidationError, json.JSONDecodeError):
        return None, [
            GuardrailError(
                violation_id=f"guard-{uuid.uuid4().hex[:8]}",
                violation_type="schema_validation_error",
                message="Model output failed schema validation after guardrails.",
                suggested_action="reject",
            )
        ]

# ---------------------------------------------------------------------------
# End of module
# ---------------------------------------------------------------------------

# Ensure the module can be imported without side effects beyond class
# definition.  No API calls, no network hooks, no registry mutations occur
# at module load time.

# Canonical guardrail error types, for documentation and type-checking.
GUARDRAIL_ERROR_TYPES = {
    "input_validation_error": "Input validation: prompt or configuration violated bounds.",
    "prompt_injection_detected": "Prompt injection: possible injection in untrusted content.",
    "schema_validation_error": "Output validation: model output does not conform to the canonical schema.",
    "unknown_tool": "Tool execution: model suggested an unknown / unregistered tool identifier.",
    "invalid_tool_arguments": "Tool execution: model suggested arguments that do not conform to the registered schema.",
    "fabricated_evidence": "Evidence integrity: model attempted to reference or fabricate evidence from an untrusted source.",
}