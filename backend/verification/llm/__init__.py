"""RL Studio LLM layer — public exports.

This package provides the shared AI infrastructure for RL Studio's
intent-verification agent, including:

- ``AIServiceInvestigator`` (``ai_investigator``): the advisory investigator, a thin adapter over the shared
  hosted ``AIService`` (Meta Model API). It is the only model transport; this package makes no HTTP request itself.
- Versioned prompt templates (``prompts``).
- Response parsing and validation (``response_parser``).
- Model output guardrails (``llm_guardrails``).
- An offline deterministic investigator (``mock_client``) used by tests and by
  environments where no Meta credentials are configured.

The public API is deliberately small and stable.  Callers depend on the
``MetaAIProvider`` protocol (``backend.verification.interfaces``), not on a transport.

Typical usage pattern:

.. code-block:: python

    from backend.verification.llm import AIServiceInvestigator, get_prompt

    prompt = get_prompt(
        "evidence_investigation",
        execution_evidence=json.dumps(evidence),
        expected_behaviour=json.dumps(requirements),
    )
    diagnosis = AIServiceInvestigator(ai_service).investigate({"prompt": prompt})

Nothing in this package performs network access or registry mutation at import
time; no API call is made unless a caller explicitly invokes a provider.
"""

from __future__ import annotations

import logging

from backend.verification.llm.ai_investigator import AIServiceInvestigator
from backend.verification.llm.llm_guardrails import (
    GUARDRAIL_ERROR_TYPES,
    GuardrailError,
    ModelOutputViolation,
    PromptInput,
    apply_guardrails,
    detect_prompt_injection,
    reject_unknown_tool,
    validate_model_output,
    validate_prompt_input,
    validate_tool_arguments,
    verify_evidence_source,
)
from backend.verification.llm.prompts import get_prompt, get_prompt_versions
from backend.verification.llm.response_parser import (
    ParsedEvidenceInvestigation,
    ParsedIntentInterpretation,
    ParsedVerificationExplanation,
    ParsedWorkflowPlan,
    ParsingFailure,
    classify_parsing_failure,
    extract_model_content,
    extract_response_metadata,
    extract_usage_from_response,
    parse_json_content,
    parse_structured_response,
)

#: Version information for the LLM layer.
llm_layer_version = "llm_v1"

#: Public prompt version identifiers, populated by ``get_prompt_versions()``.
prompt_versions: dict[str, str] = get_prompt_versions()

__all__ = [
    "AIServiceInvestigator",
    "GUARDRAIL_ERROR_TYPES",
    "GuardrailError",
    "ModelOutputViolation",
    "ParsedEvidenceInvestigation",
    "ParsedIntentInterpretation",
    "ParsedVerificationExplanation",
    "ParsedWorkflowPlan",
    "ParsingFailure",
    "PromptInput",
    "apply_guardrails",
    "classify_parsing_failure",
    "detect_prompt_injection",
    "extract_model_content",
    "extract_response_metadata",
    "extract_usage_from_response",
    "get_prompt",
    "get_prompt_versions",
    "llm_layer_version",
    "parse_json_content",
    "parse_structured_response",
    "prompt_versions",
    "reject_unknown_tool",
    "validate_model_output",
    "validate_prompt_input",
    "validate_tool_arguments",
    "verify_evidence_source",
]

#: Mapping of public names to their implementing modules, for introspection
#: and test injection.
_module_map: dict[str, str] = {
    "ai_investigator": "backend.verification.llm.ai_investigator",
    "mock_client": "backend.verification.llm.mock_client",
    "prompts": "backend.verification.llm.prompts",
    "response_parser": "backend.verification.llm.response_parser",
    "llm_guardrails": "backend.verification.llm.llm_guardrails",
}

logger = logging.getLogger(__name__)
