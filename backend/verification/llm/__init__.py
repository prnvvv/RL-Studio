"""RL Studio LLM layer - public exports.

This package provides the shared AI infrastructure for RL Studio's
intent-verification agent, including:

- MetaAIProviderProtocol and the concrete MetaAIProviderDirect
  implementation (MetaAIProviderLangChain is conditional on
  langchain_openai availability).
- Versioned prompt templates (prompts.py).
- Response parsing and validation (response_parser.py).
- Model output guardrails (llm_guardrails.py).
- Convenience shims for model invocation.

The public API is deliberately small and stable. Callers should depend
on the protocol abstraction, not on concrete provider classes, so that
the underlying integration can be swapped (LangChain -> direct SDK or
vice versa) without changing callers.

Typical usage pattern:

.. code-block:: python

    from backend.verification.llm import (
        invoke_model,
        get_prompt,
        get_prompt_versions,
        apply_guardrails,
    )
    from backend.verification.models import VerificationRequirement

    # 1. Get a prompt template and fill variables.
    prompt = get_prompt(
        "intent_interpretation",
        description=developer_description,
    )

    # 2. Invoke the model through the shared provider.
    response, usage = invoke_model(
        model="muse-spark-1.3",
        messages=[{"role": "user", "content": prompt}],
    )

    # 3. Parse and validate the response.
    from backend.verification.llm.response_parser import parse_structured_response
    from backend.verification.models import ParsedIntentInterpretation
    parsed, metadata = parse_structured_response(
        response,
        target_model=ParsedIntentInterpretation,
    )

    # 4. Apply guardrails.
    from backend.verification.llm.llm_guardrails import (
        apply_guardrails,
        PromptInput,
        GuardrailError,
    )
    from pydantic import BaseModel

    # Define a minimal canonical model for the interpretation result.
    class _InterpretationResult(BaseModel):
        goals: List[str] = []
        expected_environment_behaviour: str = ""
        ...

    validated, guardrail_errors = apply_guardrails(
        prompt_input=PromptInput(
            system_instruction="You are an RL verification analyst.",
            user_content=developer_description or "",
        ),
        raw_model_output=response.get("choices", [{}])[0].get("message", {}).get("content", ""),
        registered_tools={"check_reward", "check_termination", "check_observation"},
        registered_tool_schemas={},
        trusted_evidence_sources={"execution_traces", "configuration"},
        canonical_model=_InterpretationResult,
    )

Each component in this package is designed to be swappable and injectable.
Tests can provide fake providers that implement MetaAIProviderProtocol
without making live API requests.
"""

from __future__ import annotations

import logging

# Import from meta_ai - some names are conditional (e.g. MetaAIProviderLangChain)
# We import them inside a try/except so the package is usable even when
# langchain_openai is not installed.
try:
    # Check if MetaAIProviderLangChain was defined in meta_ai
    import backend.verification.llm.meta_ai as _ma  # type: ignore[import]
    from backend.verification.llm.meta_ai import (  # type: ignore[import]
        MetaAIProviderDirect,
        MetaAIProviderProtocol,
        get_meta_ai_provider,
        invoke_model,
    )
    if hasattr(_ma, "MetaAIProviderLangChain"):  # type: ignore[attr-defined]
        from backend.verification.llm.meta_ai import MetaAIProviderLangChain  # type: ignore[import]
    else:
        MetaAIProviderLangChain = None  # type: ignore[assignment]
    # Prompt-related imports
    # LLM guardrails imports
    from backend.verification.llm.llm_guardrails import (  # type: ignore[import]
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
    from backend.verification.llm.prompts import (  # type: ignore[import]
        get_prompt,
        get_prompt_versions,
    )

    # Response parser imports
    from backend.verification.llm.response_parser import (  # type: ignore[import]
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
except Exception:  # broad - keep package importable even if meta_ai has issues  # noqa: BLE001
    MetaAIProviderProtocol = None  # type: ignore[assignment]
    MetaAIProviderDirect = None  # type: ignore[assignment]
    MetaAIProviderLangChain = None  # type: ignore[assignment]
    get_meta_ai_provider = None  # type: ignore[assignment]
    invoke_model = None  # type: ignore[assignment]
    get_prompt = None  # type: ignore[assignment]
    get_prompt_versions = None  # type: ignore[assignment]
    extract_model_content = None  # type: ignore[assignment]
    extract_usage_from_response = None  # type: ignore[assignment]
    extract_response_metadata = None  # type: ignore[assignment]
    parse_json_content = None  # type: ignore[assignment]
    parse_structured_response = None  # type: ignore[assignment]
    classify_parsing_failure = None  # type: ignore[assignment]
    ParsingFailure = None  # type: ignore[assignment]
    ParsedIntentInterpretation = None  # type: ignore[assignment]
    ParsedWorkflowPlan = None  # type: ignore[assignment]
    ParsedEvidenceInvestigation = None  # type: ignore[assignment]
    ParsedVerificationExplanation = None  # type: ignore[assignment]
    PromptInput = None  # type: ignore[assignment]
    ModelOutputViolation = None  # type: ignore[assignment]
    validate_model_output = None  # type: ignore[assignment]
    reject_unknown_tool = None  # type: ignore[assignment]
    validate_tool_arguments = None  # type: ignore[assignment]
    verify_evidence_source = None  # type: ignore[assignment]
    detect_prompt_injection = None  # type: ignore[assignment]
    GuardrailError = None  # type: ignore[assignment]
    apply_guardrails = None  # type: ignore[assignment]
    GUARDRAIL_ERROR_TYPES = None  # type: ignore[assignment]

#: Version information for the LLM layer.
llm_layer_version = "llm_v1"

#: Public prompt version identifiers.
prompt_versions = None  # populated at runtime by get_prompt_versions()

#: Protocol abstraction for the Meta Model API provider.
#: Callers depend on this protocol, not on concrete SDK classes.
_meta_provider_protocol: MetaAIProviderProtocol | None = None


def _ensure_protocol() -> None:
    """Lazy initialiser for the protocol name reference."""
    global _meta_provider_protocol
    if _meta_provider_protocol is None:
        _meta_provider_protocol = MetaAIProviderProtocol  # type: ignore[assignment]


_ensure_protocol()

# Export the public API names.
__all__ = [
    "GUARDRAIL_ERROR_TYPES",
    "GuardrailError",
    "MetaAIProviderDirect",
    "MetaAIProviderLangChain",
    "MetaAIProviderProtocol",
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
    "get_meta_ai_provider",
    "get_prompt",
    "get_prompt_versions",
    "invoke_model",
    "llm_layer_version",
    "parse_json_content",
    "parse_structured_response",
    "reject_unknown_tool",
    "validate_model_output",
    "validate_prompt_input",
    "validate_tool_arguments",
    "verify_evidence_source",
]

#: Mapping of public names to their implementing modules, for introspection
# and test injection.
_module_map: dict[str, str] = {
    "meta_ai": "backend.verification.llm.meta_ai",
    "prompts": "backend.verification.llm.prompts",
    "response_parser": "backend.verification.llm.response_parser",
    "llm_guardrails": "backend.verification.llm.llm_guardrails",
}

logger = logging.getLogger(__name__)
logger.info("RL Studio LLM layer initialised (v%s)", llm_layer_version)

# Ensure the module can be imported without side effects beyond class
# definition and the harmless log line above. No API calls, no network
# hooks, no registry mutations occur at module load time.

#: End of module