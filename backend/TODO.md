# Person 3 — Autonomous Verification and Diagnosis Agent

## 1. Mission

Build an independent, extensible, evidence-driven AI agent that understands a developer's intended RL environment and agent behaviour, observes actual execution, autonomously plans and performs verification workflows, detects discrepancies, investigates potential root causes using Meta AI, and generates validated evidence packages for Person 4.

The system must combine:

1. Rule-based verification for deterministic checks and known invariants.
2. AI-agent reasoning for intent interpretation, workflow planning, adaptive investigation, and evidence-based diagnosis.
3. ML/DL techniques for behavioural analysis and anomaly detection where sufficient data and appropriate evaluation methods are available.

The system must not simply accept configuration values, generate a confidence score, and declare the environment correct or faulty.

It must execute a structured workflow, validate its findings, identify uncertainty, and preserve traceable evidence.

## 2. Strict File Ownership

Person 3 may create and modify files only inside:

- `backend/verification/`
- `backend/diagnosis/`

Do not modify files outside these directories.

Do not modify:
- `backend/main.py`
- Shared API routes or schemas outside the permitted folders.
- Person 2's environment, training, monitoring, or fault-injection implementation.
- Person 4's database, provenance, recovery, or evaluation implementation.
- Frontend files.
- Repository-level configuration or dependency manifests.

If an external dependency, API contract, or configuration change is required, document the requirement and coordinate with the responsible owner. Do not implement the change outside the permitted folders.

Before implementation, inspect the existing repository and reuse its established interfaces where possible.

## 3. Proposed Module Structure

```text
backend/
├── verification/
│   ├── __init__.py
│   ├── models.py
│   ├── input_adapter.py
│   ├── intent_parser.py
│   ├── context_builder.py
│   ├── requirement_registry.py
│   ├── workflow_planner.py
│   ├── rules.py
│   ├── checks.py
│   ├── execution_analyzer.py
│   ├── anomaly_detector.py
│   ├── validator.py
│   ├── engine.py
│   ├── interfaces.py
│   ├── storage.py
│   └── exceptions.py
│
└── diagnosis/
    ├── __init__.py
    ├── models.py
    ├── incident_detector.py
    ├── classifier.py
    ├── evidence_builder.py
    ├── evidence_validator.py
    ├── investigation_planner.py
    ├── meta_ai.py
    ├── prompts.py
    ├── investigation_tools.py
    ├── investigation_engine.py
    ├── diagnosis_validator.py
    ├── report_builder.py
    ├── storage.py
    └── exceptions.py
```

This is a proposed target structure. Inspect existing files before creating anything. Reuse, extend, or reorganize existing modules only within the two permitted folders.

## 4. Phase One — Input Abstraction and Extensibility

### `verification/input_adapter.py`

- [ ] Accept the structured environment and agent configuration supplied by Person 2.
- [ ] Accept optional natural-language intent from the developer.
- [ ] Accept additional runtime observations, metrics, events, logs, and activity records.
- [ ] Normalize supported input representations into a consistent internal format.
- [ ] Preserve unknown fields rather than silently discarding new variables.
- [ ] Distinguish absent, null, invalid, and explicitly empty values.
- [ ] Support optional fields without requiring every producer to supply every variable.
- [ ] Validate known fields without rejecting unrelated future extensions.
- [ ] Attach source, timestamp, run identifier, and environment version when available.
- [ ] Reject malformed or unsafe inputs with actionable errors.
- [ ] Avoid making assumptions about Person 2's final schema before coordination.

### `verification/models.py`

- [ ] Define extensible models for incoming context, declared intent, observations, requirements, workflows, check results, and verification reports.
- [ ] Support versioned data contracts.
- [ ] Preserve unrecognized input fields in an explicit extension structure or equivalent mechanism.
- [ ] Define stable identifiers for requirements and verification runs.
- [ ] Separate developer intent from observed execution data.
- [ ] Separate observed facts from inferred conclusions.
- [ ] Support explicit missing-evidence and unsupported-requirement states.
- [ ] Add serialization and deserialization tests.

### `verification/interfaces.py`

- [ ] Define stable interfaces for incoming execution evidence.
- [ ] Define interfaces for verification results and evidence references.
- [ ] Define a handoff contract for diagnosis.
- [ ] Define the interface through which Person 4 can consume incident and evidence packages.
- [ ] Avoid importing or modifying files outside the permitted directories.
- [ ] Document any external contract that still requires agreement.

**Completion criteria:** New optional fields can be introduced without breaking existing supported inputs, and the system does not silently interpret unknown fields as verified requirements.

## 5. Phase Two — Intent Understanding

### `verification/intent_parser.py`

- [ ] Interpret optional natural-language developer intent using the configured Meta AI provider through a controlled interface.
- [ ] Incorporate structured environment and agent configuration into the interpretation context.
- [ ] Identify intended objectives, constraints, expected behaviours, and success criteria.
- [ ] Extract explicit thresholds and invariants when they are stated.
- [ ] Distinguish explicit developer requirements from assumptions and suggestions.
- [ ] Identify ambiguous, contradictory, and unsupported requirements.
- [ ] Produce structured, machine-readable intent.
- [ ] Preserve the source text and traceability of extracted requirements.
- [ ] Request clarification or mark a requirement unresolved when essential information is ambiguous.
- [ ] Never invent a requirement and silently treat it as developer intent.
- [ ] Validate the output against a stable internal model.

### `verification/context_builder.py`

- [ ] Combine normalized intent with relevant configuration and execution metadata.
- [ ] Preserve the source of every input.
- [ ] Avoid confusing expected values with observed values.
- [ ] Detect contradictions between natural-language intent and structured configuration.
- [ ] Represent unresolved conflicts explicitly.
- [ ] Provide a bounded, relevant context for the workflow planner.
- [ ] Exclude secrets and irrelevant information.

**Completion criteria:** The system can transform supported natural-language intent and structured configuration into explicit, traceable verification requirements.

## 6. Phase Three — Requirement Registry and Workflow Planning

### `verification/requirement_registry.py`

- [ ] Define the supported categories of requirements.
- [ ] Associate requirements with applicable verification checks.
- [ ] Record required evidence and evaluation methods.
- [ ] Support new requirement types without rewriting the core engine.
- [ ] Track unsupported requirements.
- [ ] Track requirements that cannot currently be evaluated.
- [ ] Preserve requirement identifiers and versions where practical.

### `verification/workflow_planner.py`

- [ ] Convert the normalized intent into an ordered verification workflow.
- [ ] Select applicable deterministic rules.
- [ ] Identify required configuration, metrics, events, logs, and behavioural observations.
- [ ] Identify dependencies between checks.
- [ ] Determine which checks can run independently.
- [ ] Identify evidence that must be collected before a check can run.
- [ ] Prioritize checks that are important, inexpensive, and informative.
- [ ] Handle missing inputs by marking checks as blocked or requesting more evidence.
- [ ] Produce a structured execution plan.
- [ ] Restrict the planner to approved, registered checks and tools.
- [ ] Prevent arbitrary code execution based on AI-generated plans.
- [ ] Make the planned workflow inspectable and auditable.

**Completion criteria:** Different supported intents can produce different verification workflows, and every planned check has a defined purpose and evidence requirement.

## 7. Phase Four — Rule-Based Verification

### `verification/rules.py`

- [ ] Implement reusable rule definitions.
- [ ] Define rule inputs, outputs, and evidence requirements.
- [ ] Define supported comparison operators and numeric tolerances.
- [ ] Support exact configuration comparisons.
- [ ] Support permitted ranges and declared invariants.
- [ ] Support evidence completeness checks.
- [ ] Keep rules independent of any specific RL algorithm.
- [ ] Document rule limitations.

### `verification/checks.py`

- [ ] Implement deterministic checks selected by the planner.
- [ ] Compare expected configuration with observed configuration.
- [ ] Check declared environment and agent constraints where evidence is available.
- [ ] Check expected and observed reward configurations.
- [ ] Validate expected episode limits and other declared settings.
- [ ] Validate required event and metric availability.
- [ ] Handle missing, malformed, incompatible, and non-finite values.
- [ ] Return structured results with evidence references.
- [ ] Distinguish failed checks from checks that could not be evaluated.
- [ ] Avoid treating low reward or poor agent performance alone as proof of a bug.

### `verification/execution_analyzer.py`

- [ ] Compare expected execution behaviour with recorded observations.
- [ ] Examine relevant event sequences, activity traces, and execution records.
- [ ] Check whether expected events occurred when evidence supports that determination.
- [ ] Identify unexpected event ordering or missing required events.
- [ ] Associate findings with the relevant run and environment version.
- [ ] Separate direct observations from inferred explanations.
- [ ] Document the limits of conclusions derived from incomplete traces.

**Completion criteria:** Known requirements can be checked deterministically, with every result linked to its inputs and evidence.

## 8. Phase Five — ML/DL-Based Anomaly Detection

### `verification/anomaly_detector.py`

- [ ] Define a pluggable interface for statistical and ML/DL anomaly detectors.
- [ ] Begin with suitable baseline methods for available reward and episode metrics.
- [ ] Detect deviations from appropriate historical or baseline behaviour when sufficient comparable data exists.
- [ ] Support feature extraction from relevant time-series and execution metrics.
- [ ] Track which features and observations contributed to a result.
- [ ] Account for stochastic RL behaviour and differences between environments or configurations.
- [ ] Separate anomaly signals from confirmed requirement violations.
- [ ] Handle insufficient data and distribution changes.
- [ ] Avoid requiring a trained deep-learning model before the system can operate.
- [ ] Add ML/DL models only when appropriate data, validation, and evaluation criteria are available.
- [ ] Measure false-positive and false-negative behaviour on labelled or controlled test scenarios.
- [ ] Keep model outputs behind a stable detector interface.

**Completion criteria:** The verification system can combine deterministic results with optional anomaly signals without allowing an unvalidated ML score to override verified facts.

## 9. Phase Six — Verification Orchestration and Validation

### `verification/validator.py`

- [ ] Validate the planned workflow before execution.
- [ ] Validate check inputs and outputs.
- [ ] Confirm that required evidence references are present.
- [ ] Validate consistency between requirements and reported results.
- [ ] Identify conflicting or unsupported conclusions.
- [ ] Verify that aggregate status follows the agreed status policy.
- [ ] Prevent missing evidence from becoming an automatic pass.

### `verification/engine.py`

- [ ] Accept normalized intent and execution context.
- [ ] Construct the verification context.
- [ ] Generate the verification workflow.
- [ ] Execute approved checks.
- [ ] Invoke applicable anomaly detectors.
- [ ] Aggregate results.
- [ ] Validate the report.
- [ ] Identify discrepancies that warrant incident investigation.
- [ ] Preserve a traceable record of the workflow and its outcomes.
- [ ] Produce a structured verification report.
- [ ] Handle partial results and execution errors.
- [ ] Remain usable independently of the diagnosis subsystem.

### Required verification states

Agree on the final names with the team, but preserve these meanings:

- `PASS`: Sufficient evidence establishes that a requirement is satisfied.
- `FAIL`: Sufficient evidence establishes that a requirement is violated.
- `UNKNOWN`: Available evidence is insufficient to evaluate the requirement.
- `BLOCKED`: The check cannot run until a dependency or required input is available.
- `ERROR`: The check failed to execute correctly.

An anomaly score must not replace these states.

**Completion criteria:** The complete verification workflow can run from normalized input through planning, execution, and validated reporting.

## 10. Phase Seven — Incident Detection and Classification

### `diagnosis/incident_detector.py`

- [ ] Consume verification reports and relevant anomaly signals.
- [ ] Determine which findings warrant incident investigation.
- [ ] Group related findings when supported by shared run, environment, or evidence identifiers.
- [ ] Avoid creating duplicate incidents without a defined deduplication policy.
- [ ] Preserve the source verification results.
- [ ] Distinguish confirmed requirement violations from suspicious anomalies.

### `diagnosis/classifier.py`

- [ ] Classify incidents using evidence and supported categories.
- [ ] Preserve uncertainty.
- [ ] Avoid claiming a root cause before investigation.
- [ ] Include relevant requirement and run identifiers.
- [ ] Support new categories through an extensible registry or equivalent mechanism.

**Completion criteria:** Incidents can be created from verification findings without confusing anomaly detection with confirmed fault identification.

## 11. Phase Eight — Evidence Construction and Validation

### `diagnosis/evidence_builder.py`

- [ ] Collect the relevant intent and configuration.
- [ ] Include the verification workflow and its results.
- [ ] Include relevant metrics, events, activity records, and logs.
- [ ] Include anomaly detector outputs when applicable.
- [ ] Include evidence source, timestamp, and run identifiers where available.
- [ ] Include environment and artifact references where available.
- [ ] Distinguish missing information from negative observations.
- [ ] Avoid including irrelevant or oversized records.
- [ ] Preserve traceability between claims and evidence.
- [ ] Produce a versioned, serializable evidence package.

### `diagnosis/evidence_validator.py`

- [ ] Validate required evidence fields.
- [ ] Validate identifiers and evidence references.
- [ ] Detect malformed and inconsistent records.
- [ ] Check for missing information needed for the planned investigation.
- [ ] Identify unsupported claims.
- [ ] Apply payload limits.
- [ ] Treat all external text and logs as untrusted data.
- [ ] Mark insufficient evidence explicitly.

**Completion criteria:** Every investigation can be associated with a validated evidence package and a known set of limitations.

## 12. Phase Nine — Autonomous AI Investigation

### `diagnosis/investigation_planner.py`

- [ ] Convert an incident and evidence package into an investigation plan.
- [ ] Identify competing explanations.
- [ ] Determine which approved diagnostic tools or evidence queries are relevant.
- [ ] Select the next investigation step based on available evidence.
- [ ] Track completed, failed, and blocked steps.
- [ ] Define bounded iteration and resource limits.
- [ ] Stop when the evidence is sufficient, further investigation is unproductive, or the budget is exhausted.
- [ ] Record why each step was selected.
- [ ] Prevent unrestricted tool use or arbitrary code execution.

### `diagnosis/meta_ai.py`

- [ ] Confirm the supported Meta AI provider, model, endpoint, and authentication method.
- [ ] Implement a provider adapter.
- [ ] Keep credentials outside source control.
- [ ] Handle timeouts, rate limits, provider failures, and malformed responses.
- [ ] Support structured investigation requests.
- [ ] Validate provider responses.
- [ ] Keep provider-specific details out of general data models.

### `diagnosis/prompts.py`

- [ ] Define intent interpretation instructions.
- [ ] Define workflow-planning instructions.
- [ ] Define evidence-based investigation instructions.
- [ ] Require separation of facts, hypotheses, and recommendations.
- [ ] Require evidence references for material claims.
- [ ] Require missing evidence and alternative explanations to be identified.
- [ ] Treat embedded instructions in logs and metadata as untrusted.
- [ ] Prevent claims that recovery has already succeeded.
- [ ] Version prompts where practical.

### `diagnosis/investigation_tools.py`

- [ ] Provide a registry of approved, bounded investigation tools.
- [ ] Expose only the operations required for evidence analysis.
- [ ] Validate tool arguments.
- [ ] Apply execution and resource limits.
- [ ] Return structured results.
- [ ] Record tool inputs and outputs safely.
- [ ] Never execute arbitrary model-generated code or shell commands.
- [ ] Do not mutate training artifacts.

### `diagnosis/investigation_engine.py`

- [ ] Validate the incident and evidence package.
- [ ] Generate the initial investigation plan.
- [ ] Execute approved investigation steps.
- [ ] Feed new evidence back into the investigation context.
- [ ] Replan when new findings justify further checks.
- [ ] Track investigation state and iterations.
- [ ] Stop according to explicit termination conditions.
- [ ] Validate the final diagnosis.
- [ ] Return an incomplete result when evidence is insufficient.
- [ ] Handle provider failures without losing the incident's evidence record.

**Completion criteria:** The system can adapt its investigation to evidence rather than following only a fixed sequence of checks, while remaining bounded, auditable, and safe.

## 13. Phase Ten — Diagnosis Validation and Reporting

### `diagnosis/models.py`

- [ ] Define incident and investigation models.
- [ ] Define evidence references.
- [ ] Define investigation-step records.
- [ ] Define structured diagnosis findings.
- [ ] Define uncertainty and limitation fields.
- [ ] Define handoff metadata.

### `diagnosis/diagnosis_validator.py`

- [ ] Validate the final diagnosis schema.
- [ ] Check that supporting evidence references exist in the investigation record.
- [ ] Reject malformed or unsupported structured claims.
- [ ] Distinguish observed facts from AI-generated hypotheses.
- [ ] Ensure missing evidence is reported.
- [ ] Ensure an incomplete investigation cannot be represented as a conclusive diagnosis.

### `diagnosis/report_builder.py`

- [ ] Produce a structured incident and diagnosis report.
- [ ] Include verification findings and anomaly signals.
- [ ] Include the investigation steps performed.
- [ ] Include evidence references.
- [ ] Include suspected root causes and alternative explanations.
- [ ] Include recommended next checks.
- [ ] Include limitations and unresolved questions.
- [ ] Include a handoff summary for Person 4.
- [ ] Preserve traceability to the originating run and environment.

**Completion criteria:** The system returns a validated, evidence-backed report that downstream components can consume without interpreting free-form AI text.

## 14. Phase Eleven — Safe Persistence

### `verification/storage.py`

- [ ] Persist verification runs, requirement results, workflow steps, and report metadata.
- [ ] Use a versioned record format.
- [ ] Use stable identifiers.
- [ ] Handle partial writes and interrupted operations safely.
- [ ] Validate records before persistence.
- [ ] Avoid overwriting unrelated records.
- [ ] Implement recovery or integrity checks appropriate to the selected storage mechanism.
- [ ] Avoid storing unnecessary secrets or sensitive information.

### `diagnosis/storage.py`

- [ ] Persist incident records, evidence-package references, investigation steps, and diagnosis reports.
- [ ] Preserve relationships between incidents, runs, and verification results.
- [ ] Record investigation status and timestamps.
- [ ] Handle duplicate submissions safely.
- [ ] Preserve completed investigation records when a subsequent investigation fails.
- [ ] Validate serialized data before writing and after reading.
- [ ] Support safe handoff of generated evidence to Person 4.

### Storage restrictions

- All newly implemented storage code must remain within `backend/verification/` or `backend/diagnosis/`.
- Do not modify shared database infrastructure.
- Do not create a third backend folder.
- Do not introduce an unapproved external database service.
- Prefer the existing approved storage interface if it can be consumed without modifying files outside the permitted directories.
- Otherwise, document and implement an appropriately isolated local persistence mechanism inside the permitted folders.
- Do not store API credentials in persisted investigation records.

**Completion criteria:** Generated verification and diagnosis data can be safely retained, retrieved, validated, and passed to downstream consumers.

## 15. Phase Twelve — Testing

### Unit testing

- [ ] Test input normalization with different optional fields.
- [ ] Test forward compatibility with additional unknown variables.
- [ ] Test intent parsing and ambiguous requirements.
- [ ] Test rule selection and deterministic checks.
- [ ] Test missing and malformed evidence.
- [ ] Test workflow planning.
- [ ] Test aggregate verification status.
- [ ] Test anomaly detector behaviour.
- [ ] Test incident creation and classification.
- [ ] Test evidence construction and validation.
- [ ] Test AI response parsing and validation.
- [ ] Test investigation planning and termination.
- [ ] Test storage integrity and interrupted writes.
- [ ] Test report generation and handoff serialization.

### Integration testing

- [ ] Test a normal run with valid intent and execution evidence.
- [ ] Test the controlled reward-scaling fault.
- [ ] Test a low-reward scenario that does not establish an environment bug.
- [ ] Test missing configuration and incomplete logs.
- [ ] Test conflicting intent and structured settings.
- [ ] Test an unexpected new optional input field.
- [ ] Test an investigation requiring multiple evidence checks.
- [ ] Test provider timeouts and malformed responses.
- [ ] Test a complete verification-to-diagnosis pipeline.
- [ ] Test persistence and reload of generated reports.
- [ ] Test handoff of validated evidence to a mock Person 4 consumer.
- [ ] Test that no code modifies files outside the two permitted folders.

### ML/DL evaluation

- [ ] Define the available datasets or controlled scenarios.
- [ ] Establish appropriate baseline methods.
- [ ] Measure false positives and false negatives where labels are available.
- [ ] Evaluate behaviour across different runs and configurations.
- [ ] Test for sensitivity to stochastic variation.
- [ ] Document data limitations and unsupported scenarios.
- [ ] Do not enable an unvalidated model as the authoritative fault detector.

### Testing rules

- Use mocked Meta AI responses for ordinary unit tests.
- Keep live-provider integration tests separate.
- Ensure tests do not require external credentials by default.
- Run relevant existing tests without modifying files outside the permitted directories.
- Record test failures and environmental blockers accurately.
- Do not claim tests passed unless they were actually executed.

## 16. Phase Thirteen — End-to-End Acceptance Test

Demonstrate the following scenario:

1. Supply structured environment and agent configuration.
2. Supply optional natural-language developer intent.
3. Supply the actual run observations, metrics, events, and logs.
4. Normalize the input without losing supported or future extension fields.
5. Generate explicit verification requirements.
6. Construct an ordered verification workflow.
7. Execute deterministic checks.
8. Run applicable anomaly detectors.
9. Validate and aggregate the results.
10. Detect and classify discrepancies.
11. Construct a versioned evidence package.
12. Plan an investigation using the available evidence.
13. Execute approved diagnostic steps through the configured Meta AI integration and investigation tools.
14. Validate the diagnosis and its evidence references.
15. Persist the verification and diagnosis records safely.
16. Produce a structured handoff package for Person 4.
17. Confirm that the handoff can be consumed without modifying Person 4's implementation.
18. Confirm that the complete workflow remains within the two permitted directories.

## 17. Definition of Done

The system is complete when:

- [ ] It accepts structured configuration and optional natural-language intent.
- [ ] It can accommodate additional input variables without unnecessary schema rewrites.
- [ ] It produces explicit, traceable requirements.
- [ ] It generates and executes a structured verification workflow.
- [ ] It combines deterministic checks with appropriately validated anomaly detection.
- [ ] It distinguishes requirement violations from statistical anomalies.
- [ ] It investigates incidents adaptively using approved AI tools.
- [ ] It does not depend on a single confidence score to make decisions.
- [ ] It validates investigation findings against available evidence.
- [ ] It records missing evidence and uncertainty explicitly.
- [ ] It safely persists generated verification and diagnosis data.
- [ ] It produces a validated handoff package for Person 4.
- [ ] Unit and integration tests cover the principal workflows and failure cases.
- [ ] No files outside `backend/verification/` and `backend/diagnosis/` have been modified by Person 3.
- [ ] Setup, interface contracts, limitations, and test results are documented.

## 18. Git Rules

Follow the repository's `AGENTS.md` and `opencode.md`.

- Work on `backend3`.
- Inspect the working tree before editing.
- Make frequent, meaningful commits.
- Keep commit messages to one line.
- Push development changes only to `backend3`.
- Create or update pull requests from `backend3` to `main`.
- Never commit directly to, push directly to, or merge into `main` without explicit authorization.
- Do not overwrite another contributor's changes.
- Review the diff to confirm that only the two permitted directories have been modified.
- Run relevant tests before committing.
- Report actual changes, tests executed, failures, and unresolved integration dependencies.

Example commit:

`feat: implement autonomous verification workflow`