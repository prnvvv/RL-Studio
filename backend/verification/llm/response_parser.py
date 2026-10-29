"""Structured response parsing and validation for RL Studio's LLM layer.

Provides a central parser for model outputs from the Meta Model API,
handling the response format used by the configured endpoint, parsing
structured responses, and validating data against existing Pydantic models.

Key design points:
- Extract the appropriate output from the selected SDK's actual response
  structure (Responses API or Chat Completions).
- Handle provider-specific nesting so callers do not need to know the
  underlying format.
- Validate parsed results against canonical RL Studio Pydantic models.
- Detect missing fields, unsupported values, incomplete or malformed output.
- Convert parsing failures into typed application errors.
- Preserve provider metadata and usage information when available.
- Avoid logging sensitive raw responses.
- Use structured-output mechanisms supported by the selected endpoint.
- Validate locally even when the API enforces a schema.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Type, TypeVar, Tuple

from pydantic import BaseModel, Field, ValidationError


from backend.verification.exceptions import (  # typed parsing errors
    MetaAIProviderError,
)

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider response extraction
# ---------------------------------------------------------------------------


def extract_model_content(response: Dict[str, Any]) -> str:
    """Extract the plain-text model content from a provider response.

    Supports both the Responses API and Chat Completions formats.
    Raises ``MetaAIProviderError`` if the response does not contain
    recognisable content.
    """
    # Chat Completions style
    if "choices" in response and isinstance(response["choices"], list):
        choice = response["choices"][0] if response["choices"] else None
        if choice and isinstance(choice, dict):
            message = choice.get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content
            # Some models wrap content in a list of content blocks
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        txt = block.get("text")
                        if isinstance(txt, str):
                            text_parts.append(txt)
                return " ".join(text_parts)
    # Responses API style
    if "output" in response and isinstance(response["output"], dict):
        output = response["output"]
        text = output.get("text")
        if isinstance(text, str):
            return text
    # Fallback: try to find any string value that looks like text
    for key, val in response.items():
        if isinstance(val, str) and len(val) > 20:
            lower = key.lower()
            if not any(s in lower for s in ["id", "request", "model", "usage"]):
                return val
    # If we get here, the response format is unrecognised.
    raise MetaAIProviderError(
        "Unable to extract model content from the API response.",
        details={"response_keys": list(response.keys())},
    )


def extract_usage_from_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """Extract token-usage metadata from a provider response.

    Returns a dict with keys such as ``prompt_tokens``, ``completion_tokens``,
    ``total_tokens`` when available.  Returns an empty dict if usage is
    not present or recognisable.
    """
    usage: Dict[str, Any] = {}
    # Chat Completions style
    if "usage" in response and isinstance(response["usage"], dict):
        u = response["usage"]
        if "prompt_tokens" in u:
            usage["prompt_tokens"] = u["prompt_tokens"]
        if "completion_tokens" in u:
            usage["completion_tokens"] = u["completion_tokens"]
        if "total_tokens" in u:
            usage["total_tokens"] = u["total_tokens"]
    # Responses API style — may nest usage under "usage" or top-level
    if not usage and "usage" in response:
        u = response["usage"]
        if isinstance(u, dict):
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if k in u:
                    usage[k] = u[k]
    return usage


def extract_response_metadata(response: Dict[str, Any]) -> Dict[str, Any]:
    """Extract non-sensitive metadata from a provider response for tracing.

    Includes request ID, model name, and any available usage info.
    Never includes raw prompt content or raw model output.
    """
    metadata: Dict[str, Any] = {
        "request_id": response.get("id") or response.get("request_id"),
        "model": response.get("model"),
    }
    usage = extract_usage_from_response(response)
    if usage:
        metadata["usage"] = usage
    return metadata


# ---------------------------------------------------------------------------
# Structured-output parsing
# ---------------------------------------------------------------------------


def parse_json_content(content: str) -> Dict[str, Any]:
    """Parse a JSON string, raising a typed error on failure."""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise MetaAIProviderError(
            f"Failed to parse model JSON output: {exc}",
            details={"raw_content": content[:200]},
        ) from exc
    return parsed


def parse_structured_response(
    response: Dict[str, Any], target_model: Type[T],
) -> Tuple[T, Dict[str, Any]]:
    """Parse a model response and validate it against a canonical Pydantic model.

    Args:
        response: The raw provider response dict.
        target_model: A Pydantic ``BaseModel`` subclass that the output should
            conform to.

    Returns:
        A 2-tuple of (validated_model, metadata).

    Raises:
        MetaAIProviderError: If the response content cannot be extracted or
            the parsed data does not validate against *target_model*.
    """
    # Step 1: extract the plain‑text content from the provider's response.
    content = extract_model_content(response)
    # Step 2: extract usage metadata for the caller.
    usage = extract_usage_from_response(response)
    # Step 3: attempt to parse the content as JSON (structured-output).
    parsed: Dict[str, Any]
    try:
        parsed = parse_json_content(content)
    except MetaAIProviderError:
        # If JSON parsing fails, re‑raise — we do not attempt automatic repair.
        raise MetaAIProviderError(
            "Model output is not valid JSON — structured-output failed.",
            details={"raw_content": content[:200]},
        )
    # Step 4: validate against the canonical model.
    try:
        validated = target_model(**parsed)
    except ValidationError as exc:
        raise MetaAIProviderError(
            f"Parsed model output does not validate against the canonical schema: {exc}",
            details={"parsed": parsed},
        ) from exc
    # Step 5: return the validated model and the extracted metadata.
    metadata = {
        "usage": usage,
        "raw_content": content,
        "parsed_successfully": True,
    }
    return validated, metadata


# ---------------------------------------------------------------------------
# Parsing failure classification
# ---------------------------------------------------------------------------


class ParsingFailure(BaseModel):
    """A structured representation of a parsing failure, so callers can
    distinguish the failure type and take appropriate action."""

    failure_type: str  # e.g. "json_parse_error", "schema_validation_error", "missing_content"
    message: str
    raw_content: Optional[str] = None
    suggested_action: str = "reject_and_report"


def classify_parsing_failure(exc: Exception, raw_content: Optional[str] = None) -> ParsingFailure:
    """Classify a parsing exception into a typed ``ParsingFailure``."""
    if isinstance(exc, MetaAIProviderError):
        return ParsingFailure(
            failure_type="meta_ai_provider_error",
            message=str(exc),
            raw_content=raw_content,
            suggested_action="reject_and_report",
        )
    if isinstance(exc, json.JSONDecodeError):
        return ParsingFailure(
            failure_type="json_parse_error",
            message=f"Failed to parse JSON from model output: {exc}",
            raw_content=raw_content,
            suggested_action="reject_and_report",
        )
    if isinstance(exc, ValidationError):
        return ParsingFailure(
            failure_type="schema_validation_error",
            message=f"Model output does not validate against the canonical schema: {exc}",
            raw_content=raw_content,
            suggested_action="reject_and_report",
        )
    # Default fallback
    return ParsingFailure(
        failure_type="unknown_parsing_error",
        message=str(exc),
        raw_content=raw_content,
        suggested_action="reject_and_report",
    )


# ---------------------------------------------------------------------------


# Canonical models for parsed results, used by response_parser to validate
# model outputs consistently across the codebase.

class ParsedIntentInterpretation(BaseModel):
    """A parsed, schema‑validated intent interpretation result."""
    goals: list = Field(default_factory=list, description="Identified goals from the developer intent")
    expected_environment_behaviour: str = Field("", description="Summary of expected warehouse/agent behaviour")
    reward_expectations: float = Field(None, description="Expected reward value or range")
    termination_conditions: list = Field(default_factory=list, description="Identified episode termination conditions")
    constraints: list = Field(default_factory=list, description="Identified constraints on agent/environment")
    numerical_thresholds: dict = Field(default_factory=dict, description="Named numerical thresholds")
    ambiguities: list = Field(default_factory=list, description="Identified ambiguities")
    conflicts: list = Field(default_factory=list, description="Identified conflicts")
    missing_information: list = Field(default_factory=list, description="Information that would help resolve uncertainties")

class ParsedWorkflowPlan(BaseModel):
    """A parsed, schema‑validated workflow plan result."""
    selected_tools: list = Field(default_factory=list, description="Registered tool identifiers selected by the model")
    rationale: dict = Field(default_factory=dict, description="Why each selected tool is relevant")
    prerequisite_evidence: list = Field(default_factory=list, description="Evidence items needed before a check can run")
    unsupported_requirements: list = Field(default_factory=list, description="Requirement IDs that are unsupported")

class ParsedEvidenceInvestigation(BaseModel):
    """A parsed, schema‑validated evidence investigation result."""
    summary: str = Field("", description="Key observations from execution evidence")
    contradictions: list = Field(default_factory=list, description="Identified contradictions")
    hypotheses: list = Field(default_factory=list, description="Proposed hypotheses")
    additional_evidence_needed: list = Field(default_factory=list, description="What additional evidence would help")

class ParsedVerificationExplanation(BaseModel):
    """A parsed, schema‑validated verification explanation result."""
    status: str = Field(..., description="One of: PASS, FAIL, UNKNOWN, BLOCKED, ERROR")
    explanation: str = Field("", description="Human-readable explanation from validated results")
    limitations: list = Field(default_factory=list, description="Identified limitations and unresolved questions")

# End of module
# ---------------------------------------------------------------------------

# Ensure the module can be imported without side effects beyond class
# definition.  No API calls, no network hooks, no registry mutations occur
# at module load time.