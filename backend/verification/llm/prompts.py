"""Versioned prompt templates for RL Studio's intent-verification agent.

Each template is a reusable, identifiable prompt that can be versioned and
tested separately.  Prompts are kept separate from API request construction
and workflow control so they can evolve independently.

Available prompt types:
- intent_interpretation: Understand developer intent for environment/agent.
- requirement_extraction: Convert intent into structured verification requirements.
- workflow_planning: Propose a verification plan using registered tools.
- evidence_investigation: Analyze observed discrepancies.
- verification_explanation: Generate human-readable explanations from results.
"""

from __future__ import annotations

import re
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Prompt version identifiers — bump when template logic or constraints change.
# These are deliberately kept as strings so tests can match on the exact
# version used for a given trace.
# ---------------------------------------------------------------------------

PROMPT_INTENT_INTERPRETATION = "intent_interpretation_v1"
PROMPT_REQUIREMENT_EXTRACTION = "requirement_extraction_v1"
PROMPT_WORKFLOW_PLANNING = "workflow_planning_v1"
PROMPT_EVIDENCE_INVESTIGATION = "evidence_investigation_v1"
PROMPT_VERIFICATION_EXPLANATION = "verification_explanation_v1"


# ---------------------------------------------------------------------------
# Helper: format a prompt with safe variable substitution.
# Untrusted evidence is passed through a separate channel; this function
# only substitutes developer-controlled or configuration values.
# ---------------------------------------------------------------------------

#: Placeholder pattern used by the partial prompt formatter.
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _render(template: str, variables: dict[str, Any]) -> str:
    """Substitute only the placeholders whose values were supplied.

    Unlike ``str.format``, a caller that supplies a subset of the variables does
    not get a ``KeyError``; the remaining placeholders stay visible so an
    incomplete call is obvious instead of silently producing an empty section.
    """

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in variables:
            return str(variables[key])
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, template)


def _safe_format(template: str, mapping: dict[str, Any]) -> str:
    """Format *template* with *mapping* via :func:`_render`.

    Untrusted evidence must never be interpolated into governing instructions;
    callers pass untrusted content through a named evidence variable only.

    This is a deliberately strict formatter: it never evaluates attribute or
    index lookups and never raises ``KeyError`` for uncovered placeholders.
    """
    return _render(template, mapping)


# ---------------------------------------------------------------------------
# A. Intent Interpretation
# Purpose: Understand the developer's intended environment and agent behavior.
# Extract: goals, expected behavior, reward expectations, termination
#   conditions, constraints, numerical thresholds, configuration requirements,
#   ambiguities, conflicts, missing information.
# ---------------------------------------------------------------------------

INTENT_INTERPRETATION_TEMPLATE = """\
You are an autonomous RL verification analyst.  Your task is to interpret
the developer's intent for a warehouse-navigation reinforcement-learning
environment and produce a structured summary.

Developer-provided description follows.
---{description}---

From this description, extract and summarise:
1. **Goals**: What does the agent need to achieve?
2. **Expected environment behavior**: What should the warehouse, rewards,
   termination, and agent actions look like in a healthy run?
3. **Reward expectations**: What reward values are expected (or ranges)?
4. **Termination conditions**: Under what circumstances should episodes end?
5. **Constraints**: Any explicit constraints on agent actions, observations,
   or environment dynamics.
6. **Numerical thresholds**: Any explicit numerical boundaries (e.g. "reward
   should be > X", "episode length < Y").
7. **Configuration requirements**: What environment or agent configuration
   parameters are needed?
8. **Ambiguities**: Any ambiguous or underspecified elements.
9. **Conflicts**: Any explicitly conflicting requirements.
10. **Missing information**: What would help resolve remaining uncertainties?

Respond with a concise, structured summary.  Do not invent numerical values
or silently resolve material ambiguity.
"""


# ---------------------------------------------------------------------------
# B. Requirement Extraction
# Purpose: Convert interpreted intent into candidate structured verification
# requirements.  Each requirement uses the existing canonical schema and
# preserves: identifier, description, expected behavior/value, applicable
# condition, source reference, explicit vs inferred, confidence/uncertainty,
# whether clarification is needed, whether supported by verification tools.
# ---------------------------------------------------------------------------

REQUIREMENT_EXTRACTION_TEMPLATE = """\
You are an autonomous RL verification requirement extractor.  Your task
is to convert the intent below into a list of candidate
structured verification requirements using the canonical RL Studio schema.

Interpreted intent summary follows.
---{intent_summary}---

From this intent summary, produce a list of requirements.  Each requirement
should include:
- **id**: A unique requirement identifier (e.g. "req_goal_reward").
- **description**: Human-readable description of the requirement.
- **expected_value**: The expected value or range (if applicable; may be
  null when no confirmed expected value exists).
- **condition**: The condition under which this requirement applies (e.g.
  "during training", "at episode end", "when goal reached").
- **source**: One of ``developer_confirmed``, ``test_derived``,
  ``code_inferred``, ``documentation_inferred``, or ``system_invariant``.
- **confidence**: A confidence score 0--1 if supported; null otherwise.
- **clarification_needed**: Boolean — true if the requirement cannot be
  resolved from the given information alone.
- **supported_by_tool**: Identifier of a registered verification tool that
  can validate this requirement, or null if none.

Only include requirements that are plausibly derivable from the intent.
Do not invent requirements or fabricate expected values.  When no applicable
confirmed contract exists, expected_value should be absent (null), not guessed.
"""


# ---------------------------------------------------------------------------
# C. Workflow Planning
# Purpose: Suggest an appropriate verification plan using the available
# requirement set, execution context, and registered verification tools.
# The model must: select only from application-provided registered tool
# identifiers, explain why each proposed check is relevant, identify
# prerequisite evidence, flag unsupported requirements, avoid repeating
# completed checks without justification, avoid inventing tool outputs.
# ---------------------------------------------------------------------------

WORKFLOW_PLANNING_TEMPLATE = """\
You are an autonomous RL verification planner.  Your task is to produce a
verification plan — a sequence of registered verification checks — given
the following requirement set, execution context, and available tools.

Requirement set follows.
---{requirements}---

Execution context follows.
---{context}---

Available registered verification tools (use only these identifiers):
---{available_tools}---

Instructions:
1. Select only from the registered tool identifiers listed above.
2. For each selected tool, explain why it is relevant to the chosen
   requirement(s).
3. Identify any prerequisite evidence needed before a check can run.
4. Flag any requirements that are unsupported by the available tools.
5. Do not repeat a check that has already been completed without a
   justified reason (the caller should track completed checks externally).
6. Do not invent tool outputs or claim that checks have already run.
7. If the requirement set is sufficient to produce a complete plan, produce
   the full sequence.  If not, identify what additional information or
   tools would be needed.

Respond with a structured plan.  Use only the tool identifiers above.
"""


# ---------------------------------------------------------------------------
# D. Evidence Investigation
# Purpose: Help analyse observed discrepancies between expected and actual
# behaviour.  The model may summarise evidence, identify contradictions,
# propose plausible hypotheses, identify additional evidence that would
# help distinguish hypotheses, and explain why a hypothesis is supported
# or unsupported.  It must distinguish observed facts from hypotheses
# and missing evidence.  It must NOT declare a root cause proven solely
# because a configuration value differs from the expected value.
# ---------------------------------------------------------------------------

EVIDENCE_INVESTIGATION_TEMPLATE = """\
You are an autonomous RL verification investigator.  Your task is to
analyse the discrepancies between expected and observed execution evidence
and produce a structured investigation report.

Execution evidence follows.
---{execution_evidence}---

Expected behaviour / requirements follow.
---{expected_behaviour}---

Instructions:
1. Summarise the key observations from the execution evidence.
2. Identify any contradictions between expected and observed values.
3. Propose plausible hypotheses that could explain the discrepancies.
4. For each hypothesis, identify what additional evidence would help
   distinguish it from alternatives.
5. Distinguish observed facts from hypotheses and from missing evidence.
6. Do NOT declare a root cause proven solely because a configuration value
   differs from the expected value.
7. Explain why a given hypothesis is supported or unsupported by the
   available evidence, and note any remaining uncertainties.

Respond with a structured investigation report.  Do not fabricate metrics,
rewards, trajectories, checkpoints, logs, or tool outputs.
"""


# ---------------------------------------------------------------------------
# E. Verification Explanation
# Purpose: Generate human-readable explanations from already validated
# results.  The prompt must use supplied results and evidence references,
# preserve the distinction between PASS, FAIL, UNKNOWN, BLOCKED, and ERROR
# statuses, avoid inventing evidence, avoid changing the authoritative
# result, and identify limitations and unresolved questions.
# ---------------------------------------------------------------------------

VERIFICATION_EXPLANATION_TEMPLATE = """\
You are an autonomous RL verification explanation generator.  Your task
is to generate a human-readable explanation from the following already
validated verification results and associated evidence.

Verification results follow.
---{verification_results}---

Key evidence references follow.
---{evidence_references}---

Instructions:
1. Use the supplied verification results (PASS, FAIL, UNKNOWN, BLOCKED,
   ERROR) and their associated evidence references verbatim — do not
   re-interpret or re-grade them.
2. Preserve the distinction between PASS, FAIL, UNKNOWN, BLOCKED, and
   ERROR statuses; do not map all outcomes to a single narrative.
3. Identify limitations and unresolved questions that remain after the
   verification.
4. Avoid inventing evidence or fabricating metrics, rewards, trajectories,
   checkpoints, logs, or tool outputs.
5. Identify any open questions that would help future verification runs.
6. Keep the explanation concise and focused on what the results show.

Respond with a structured explanation.  Do not change the authoritative
result or invent new evidence.
"""


# ---------------------------------------------------------------------------
# Prompt factory — return a prompt template by name.
# ---------------------------------------------------------------------------

def get_prompt(
    name: Literal[
        "intent_interpretation",
        "requirement_extraction",
        "workflow_planning",
        "evidence_investigation",
        "verification_explanation",
    ],
    **variables: Any,
) -> str:
    """Return the named prompt template with *variables* substituted safely.

    Only the supplied ``**variables`` are substituted; any other placeholder is
    left in place so a caller can see which inputs are still missing.  This
    keeps prompt assembly total: a partial call never raises ``KeyError``.

    Raises:
        ValueError: If *name* does not correspond to a known prompt.
    """
    templates: dict[str, str] = {
        "intent_interpretation": INTENT_INTERPRETATION_TEMPLATE,
        "requirement_extraction": REQUIREMENT_EXTRACTION_TEMPLATE,
        "workflow_planning": WORKFLOW_PLANNING_TEMPLATE,
        "evidence_investigation": EVIDENCE_INVESTIGATION_TEMPLATE,
        "verification_explanation": VERIFICATION_EXPLANATION_TEMPLATE,
    }
    if name not in templates:
        raise ValueError(f"Unknown prompt name: {name!r}. Known: {list(templates.keys())}")
    return _render(templates[name], variables)


# ---------------------------------------------------------------------------
# Prompt versioning — export the version identifiers so tests and traces can
# establish which prompt version was used.
# ---------------------------------------------------------------------------

def get_prompt_versions() -> dict[str, str]:
    """Return a mapping of prompt names to their version identifiers."""
    return {
        "intent_interpretation": PROMPT_INTENT_INTERPRETATION,
        "requirement_extraction": PROMPT_REQUIREMENT_EXTRACTION,
        "workflow_planning": PROMPT_WORKFLOW_PLANNING,
        "evidence_investigation": PROMPT_EVIDENCE_INVESTIGATION,
        "verification_explanation": PROMPT_VERIFICATION_EXPLANATION,
    }


# ---------------------------------------------------------------------------
# End of module
# ---------------------------------------------------------------------------

# Ensure the module can be imported without side effects beyond class
# definition.  No API calls, no network hooks, no registry mutations occur
# at module load time.