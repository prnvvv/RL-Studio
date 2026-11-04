# Self-Healing RL Studio
# Person 3 — Autonomous Verification and Diagnosis Architecture

## 1. Purpose

Person 3 is responsible for implementing an independent verification and diagnosis subsystem for Self-Healing RL Studio.

The subsystem receives developer intent, environment and agent configuration, and actual execution evidence from Person 2. It converts these inputs into explicit requirements, plans and executes verification workflows, identifies discrepancies, investigates incidents using Meta AI, and generates validated evidence packages for Person 4.

This is not a simple rule checker, confidence calculator, or LLM wrapper.

It is a bounded, evidence-driven AI agent that can determine what to check, execute appropriate checks, evaluate the results, identify missing information, select further investigations, and produce a structured conclusion.

The implementation combines:

1. Rule-based systems for deterministic verification.
2. AI agents for intent interpretation, workflow planning, and adaptive diagnosis.
3. ML/DL techniques for detecting behavioural anomalies that may not be captured by predefined rules.

These components must work together through explicit interfaces and validation stages.

---

## 2. Strict Implementation Boundary

Person 3 may create and modify files only inside these two directories:

```text
backend/
├── verification/
└── diagnosis/
```

The implementation must not modify files outside these directories.

Specifically, do not modify:

- Backend entry points.
- Shared API routes or schemas located elsewhere.
- Person 2's environment, training, monitoring, or fault-injection code.
- Person 4's database, provenance, recovery, or evaluation code.
- Frontend files.
- Repository-level dependency manifests or configuration files.

Existing interfaces may be consumed if they are accessible without modifying their implementation.

If an integration requires a change outside these directories, document the requirement and coordinate with the responsible team member. Do not implement that change yourself.

The exact existing directory structure must be inspected before adding files. Reuse existing modules when possible.

---

## 3. System Objectives

The subsystem must:

1. Understand the developer's intended behaviour.
2. Incorporate structured environment and agent configuration.
3. Accept actual execution observations, including metrics, events, logs, activity traces, and other available evidence.
4. Remain compatible with additional input variables introduced in future iterations.
5. Convert intent into explicit, traceable verification requirements.
6. Generate a workflow appropriate to the requirements and available evidence.
7. Execute deterministic verification checks.
8. Use statistical or ML/DL-based anomaly detection when appropriate.
9. Aggregate and validate results.
10. Detect and classify discrepancies.
11. Construct a traceable evidence package.
12. Plan and conduct an adaptive investigation using Meta AI and approved tools.
13. Validate the resulting diagnosis.
14. Persist generated records safely.
15. Produce a structured handoff for Person 4.

The subsystem must not equate a low reward, an anomaly score, or an AI-generated hypothesis with proof of an environment defect.

---

## 4. Proposed Directory Structure

```text
backend/
│
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

This is a proposed logical structure. Existing files may fulfil some of these responsibilities already.

Do not create duplicate modules simply to match the proposed names.

---

## 5. High-Level Architecture

```text
                    INPUTS FROM PERSON 2
                             |
              +--------------+---------------+
              |              |               |
              v              v               v
        Environment       Agent          Execution
        Configuration   Configuration    Evidence
              |              |               |
              +--------------+---------------+
                             |
                             v
                  +----------------------+
                  | Input Adapter        |
                  | input_adapter.py     |
                  +----------------------+
                             |
                             v
                  +----------------------+
                  | Context Builder      |
                  | context_builder.py   |
                  +----------------------+
                             |
                 +-----------+-----------+
                 |                       |
                 v                       v
          Natural-Language        Structured Config
          Intent Interpretation   and Observations
                 |                       |
                 +-----------+-----------+
                             |
                             v
                  +----------------------+
                  | Intent Parser        |
                  | intent_parser.py     |
                  +----------------------+
                             |
                             v
                  +----------------------+
                  | Requirement Registry |
                  | requirement_registry |
                  +----------------------+
                             |
                             v
                  +----------------------+
                  | Workflow Planner     |
                  | workflow_planner.py  |
                  +----------------------+
                             |
                             v
                  +----------------------+
                  | Verification Engine  |
                  | engine.py            |
                  +----------------------+
                             |
               +-------------+-------------+
               |             |             |
               v             v             v
           Rule-Based     Execution      ML/DL
            Checks        Analysis       Detector
               |             |             |
               +-------------+-------------+
                             |
                             v
                  +----------------------+
                  | Result Validator     |
                  | validator.py        |
                  +----------------------+
                             |
                             v
                  +----------------------+
                  | Incident Detection   |
                  | and Classification   |
                  +----------------------+
                             |
                             v
                  +----------------------+
                  | Evidence Builder     |
                  | evidence_builder.py  |
                  +----------------------+
                             |
                             v
                  +----------------------+
                  | Evidence Validator   |
                  | evidence_validator   |
                  +----------------------+
                             |
                             v
                  +----------------------+
                  | Investigation        |
                  | Planner              |
                  +----------------------+
                             |
                             v
                  +----------------------+
                  | Investigation Engine |
                  +----------------------+
                             |
                +------------+------------+
                |                         |
                v                         v
           Approved Tools            Meta AI
                |                         |
                +------------+------------+
                             |
                             v
                  +----------------------+
                  | Diagnosis Validator  |
                  +----------------------+
                             |
                             v
                  +----------------------+
                  | Report Builder       |
                  +----------------------+
                             |
                  +----------+-----------+
                  |                      |
                  v                      v
           Safe Persistence       Person 4 Handoff
                  |
                  v
          Auditable Records
```

This diagram represents logical components and their responsibilities. It does not require every component to be implemented as a separate AI agent.

The verification planner and investigation planner may use the same underlying Meta AI provider while remaining separate components with different objectives and tool permissions.

---

## 6. Input Abstraction and Forward Compatibility

### 6.1 Input sources

The system must accept the information made available by Person 2, including:

**Developer intent**
- Optional natural-language description.
- Expected agent behaviour.
- Expected environment behaviour.
- Objectives and constraints.
- Declared success criteria.

**Environment configuration**
- Environment identifier and version.
- State and observation definitions.
- Action-space configuration.
- Reward settings.
- Episode limits.
- Termination conditions.
- Other supported environment settings.

**Agent configuration**
- Algorithm identifier.
- Policy configuration.
- Hyperparameters.
- Training settings.
- Exploration settings, when available.
- Other supported agent settings.

**Execution evidence**
- Training run identifiers.
- Reward and episode metrics.
- Recorded actions and observations.
- Environment events.
- Training logs.
- Activity traces.
- Configuration snapshots.
- Available fault-injection metadata.
- Other execution evidence introduced later.

These fields are examples of possible inputs, not an assumption that Person 2 will provide every field.

### 6.2 Input adapter

`verification/input_adapter.py` is the boundary between Person 2's data and Person 3's internal models.

It should:

1. Accept supported input representations.
2. Validate known fields.
3. Normalize supported values.
4. Preserve unknown extension fields.
5. Distinguish absent fields from explicit null values.
6. Attach source metadata where available.
7. Reject malformed or unsafe inputs.
8. Avoid silently discarding new information.

### 6.3 Extensible data models

`verification/models.py` should define stable internal models while permitting additional producer-specific fields.

A suitable design is a versioned core schema plus an extension mechanism.

For example:

```json
{
  "schema_version": "1.0",
  "run_id": "run_001",
  "environment": {
    "id": "warehouse",
    "version": "v1",
    "config": {
      "reward_scale": 100,
      "max_episode_steps": 500
    },
    "extensions": {
      "future_environment_parameter": "example"
    }
  },
  "agent": {
    "algorithm": "PPO",
    "config": {
      "learning_rate": 0.0003
    },
    "extensions": {}
  },
  "developer_intent": {
    "text": "The agent should reach the target while avoiding obstacles."
  },
  "execution_evidence": {
    "metrics": [],
    "events": [],
    "logs": []
  }
}
```

This is an illustrative internal representation, not a claim about Person 2's final schema.

The implementation should avoid assuming that the example fields are always present.

### Forward-compatibility requirements

- Unknown optional fields must not break otherwise valid inputs.
- Known fields must still be validated.
- Unknown values must not automatically become verification requirements.
- New field types must be registered or handled explicitly before being used in deterministic comparisons.
- Missing required information must be reported.
- Schema evolution must be traceable through versions or equivalent metadata.

---

## 7. Intent Understanding

**Files:** `verification/intent_parser.py`, `verification/context_builder.py`

The purpose of intent understanding is to determine what the developer expects the agent and environment to do.

### Inputs

- Optional natural-language intent.
- Structured environment configuration.
- Structured agent configuration.
- Declared constraints and success criteria.
- Existing execution context, when available.

### Processing

The intent interpretation component should:

1. Identify the developer's objective.
2. Extract explicit requirements.
3. Identify behavioural constraints.
4. Identify expected configuration values where specified.
5. Identify measurable success criteria.
6. Separate explicit requirements from inferred assumptions.
7. Identify ambiguous or contradictory statements.
8. Record which input supports each extracted requirement.
9. Mark unsupported requirements as unresolved.
10. Produce a structured representation suitable for workflow planning.

### Structured requirement example

Natural-language input:

"The agent should reach the target without crossing obstacles. Reaching the target should produce a positive reward."

Possible structured interpretation:

```json
{
  "requirements": [
    {
      "id": "target_reachability",
      "type": "behavioral",
      "description": "The target must be reachable.",
      "source": "developer_intent",
      "verification_method": "environment_reachability_check"
    },
    {
      "id": "obstacle_avoidance",
      "type": "behavioral",
      "description": "The agent must avoid obstacles.",
      "source": "developer_intent",
      "verification_method": "trajectory_constraint_check"
    },
    {
      "id": "target_reward",
      "type": "reward",
      "description": "Reaching the target should produce a positive reward.",
      "source": "developer_intent",
      "verification_method": "reward_configuration_and_event_check"
    }
  ]
}
```

These are candidate interpretations. Each requirement must be checked for ambiguity and supported by appropriate evidence before being treated as a verified constraint.

### Handling ambiguity

Suppose the developer says:

"The agent should learn quickly."

This statement is not sufficiently precise to establish a deterministic pass or failure.

The system may identify potential measurements such as:
- Steps required to reach a target success rate.
- Success rate after a declared training budget.
- Reward progression over a specified interval.

However, it must not invent a threshold and silently attribute it to the developer.

The requirement should remain unresolved until an explicit threshold, a pre-approved project policy, or a justified evaluation criterion is available.

---

## 8. Requirement Registry and Workflow Planning

**Files:** `verification/requirement_registry.py`, `verification/workflow_planner.py`

A requirement registry maps recognized requirement types to approved verification methods.

For example:

| Requirement | Verification method |
|---|---|
| Reward configuration must match a declared value | Deterministic configuration check |
| Maximum episode length must not exceed a declared limit | Configuration and execution check |
| Target must be reachable | Environment reachability check, if the environment interface supports it |
| Agent must avoid obstacles | Trajectory constraint check |
| Reward behaviour must remain within an expected distribution | Statistical analysis, given appropriate observations |
| Training behaviour differs substantially from a baseline | Baseline comparison or anomaly detection, if comparable data exists |

The workflow planner converts the requirements into an ordered plan.

A workflow step should identify:

- Step identifier.
- Requirement identifier.
- Verification method.
- Required inputs.
- Dependencies.
- Expected result type.
- Execution status.
- Evidence references.
- Failure or blocking reason, when applicable.

### Adaptive planning

The planner should not always execute every available check.

Instead, it should select the checks relevant to the current intent and evidence.

For example:

- A reward configuration mismatch may first require confirmation of the active configuration.
- A behavioural mismatch may require trajectory evidence.
- A suspicious reward trend may require more observations or a baseline comparison.
- Missing execution records may require a request for additional evidence.

The planner may use Meta AI to propose a workflow, but the generated plan must be validated against a registry of supported checks.

The system must not execute arbitrary code merely because the model proposed it.

---

## 9. Rule-Based Verification

**Files:** `verification/rules.py`, `verification/checks.py`

Rule-based verification is responsible for deterministic conclusions.

### Responsibilities

- Compare declared and observed configuration values.
- Evaluate supported numeric ranges.
- Validate required configuration fields.
- Check explicit invariants.
- Validate event-sequence requirements when sufficient evidence exists.
- Check whether required execution evidence is available.
- Identify inconsistencies between related records.

### Example

Developer requirement:

```text
Expected reward scale = 100
```

Observed configuration:

```text
Reward scale = 25
```

Verification:

```text
Status: FAIL

Reason:
The observed reward scale differs from the declared value.

Evidence:
The requirement definition and the recorded active
configuration for the relevant training run.
```

This establishes a configuration discrepancy if the values and run association are valid.

It does not establish why the discrepancy occurred.

### Verification statuses

The internal contract should distinguish:

- `PASS`
- `FAIL`
- `UNKNOWN`
- `BLOCKED`
- `ERROR`

The exact names may be adapted to the shared contract, but their meanings must remain distinct.

A missing observation must not be treated as a pass. An internal exception must not be treated as proof that the environment is faulty.

---

## 10. Execution Analysis and ML/DL Anomaly Detection

**Files:** `verification/execution_analyzer.py`, `verification/anomaly_detector.py`

Execution analysis examines actual recorded behaviour.

Potential inputs include:
- Reward sequences.
- Episode lengths.
- Success and failure events.
- Recorded state transitions.
- Action and observation traces.
- Environment events.
- Configuration changes.
- Relevant training metrics.

### Execution analysis

The execution analyzer should:
- Associate records with the correct run.
- Check supported event sequences.
- Identify missing expected events where evidence permits.
- Identify violations of explicit behavioural constraints.
- Distinguish direct observations from inferences.
- Preserve the source of each finding.

### ML/DL anomaly detection

The anomaly detector should expose a stable interface so different methods can be introduced without changing the verification engine.

Possible methods include:
- Statistical baselines.
- Rolling-window deviation detection.
- Distribution-shift detection.
- Suitable anomaly-detection models.
- Learned behavioural models, when sufficient training data exists.

These methods are options, not mandatory dependencies for the first working version.

### Important constraints

1. An anomaly score is a signal, not proof of a fault.
2. Training data must be relevant to the environment and behaviour being evaluated.
3. Stochastic variation must be considered.
4. Insufficient data must be reported.
5. False positives and false negatives must be evaluated where labelled scenarios are available.
6. ML/DL results must not silently override deterministic requirement violations.
7. The system must remain usable when an optional model is unavailable.

For example, a sudden reward decline may trigger an investigation. A separate configuration check or further behavioural evidence is needed to establish whether the decline resulted from an environment defect.

---

## 11. Verification Engine

**Files:** `verification/engine.py`, `verification/validator.py`

The verification engine coordinates the complete verification workflow.

### Execution procedure

1. Receive the input package.
2. Normalize and validate the input.
3. Construct the verification context.
4. Interpret developer intent.
5. Produce structured requirements.
6. Identify applicable verification methods.
7. Plan the workflow.
8. Validate the plan.
9. Execute approved deterministic checks.
10. Execute applicable behavioural analyses.
11. Execute available anomaly detectors.
12. Aggregate results.
13. Validate the aggregate report.
14. Identify discrepancies requiring investigation.
15. Persist the result through the approved local storage interface.
16. Return a structured verification report.

### Validation responsibilities

The validator should check that:

- Required workflow steps have valid results.
- Check results use recognized statuses.
- Required evidence references are present.
- Aggregate status is consistent with individual results.
- Missing information is not represented as a successful check.
- Unsupported requirements remain unresolved.
- Anomaly signals are not misrepresented as confirmed faults.

### Overall verification status

An overall report must not indicate complete success when required checks have failed, remain unresolved, or could not execute.

The report should preserve individual results so downstream components can understand exactly what passed, failed, or remained unknown.

---

## 12. Incident Detection and Classification

**Files:** `diagnosis/incident_detector.py`, `diagnosis/classifier.py`

The incident detector consumes verification reports and relevant anomaly signals.

Its job is to identify findings that warrant investigation.

### Incident triggers

Potential triggers include:
- A confirmed requirement violation.
- An explicit environment invariant being violated.
- A suspicious execution pattern that requires investigation.
- Missing evidence preventing a critical requirement from being evaluated.
- Conflicting records that undermine verification.

Not every trigger has the same severity or certainty.

The classifier must preserve the difference between a confirmed discrepancy and a possible anomaly.

### Incident record

A conceptual incident record may include:

```json
{
  "incident_id": "incident_001",
  "run_id": "run_001",
  "category": "CONFIGURATION_MISMATCH",
  "status": "detected",
  "summary": "Observed reward scale differs from expected value.",
  "verification_references": [
    "check_reward_scale"
  ],
  "evidence_references": [
    "observation_001"
  ]
}
```

The final field names and categories must follow the agreed contract.

The incident record should not assert a root cause before the diagnosis process has investigated the evidence.

---

## 13. Evidence Construction and Validation

**Files:** `diagnosis/evidence_builder.py`, `diagnosis/evidence_validator.py`

The evidence builder collects the information needed for diagnosis.

### Evidence may include

- Original developer intent.
- Normalized requirements.
- Relevant environment and agent configuration.
- Run and environment identifiers.
- Verification workflow and check results.
- Relevant reward and episode metrics.
- Execution events and activity traces.
- Relevant log excerpts.
- Anomaly detection results.
- Configuration and source-code references, where available.
- Artifact and provenance references supplied by Person 4.
- Missing evidence and unresolved questions.

### Evidence provenance

Where available, each item should retain:
- Evidence identifier.
- Source.
- Associated run or environment.
- Timestamp.
- Relevant requirement or incident.
- Reference to the underlying record.

Do not fabricate provenance fields when the source did not provide them.

### Evidence validation

Before investigation, validate that:
- The package is structurally valid.
- Identifiers are consistent.
- Evidence references are resolvable or explicitly marked unavailable.
- The package stays within configured size limits.
- Required evidence is present for the intended investigation.
- Missing evidence is recorded.
- Untrusted text cannot override the system's investigation instructions.

The system should be able to investigate incomplete evidence packages, but the resulting diagnosis must explicitly reflect the limitations.

---

## 14. Autonomous Diagnosis Agent

> **Implementation status:** the implemented diagnosis is a bounded, advisory LangGraph workflow in `backend/diagnosis/` (`load_context -> reuse_check -> gate -> reason -> ground -> persist`) exposed by `POST /api/v1/incidents/{incident_id}/investigations` and `/recovery-recommendations`. It makes one evidence-grounded Muse Wonder call per distinct evidence context; it has no autonomous tool loop. The planner, engine and tools files below are not implemented.

**Files:** `diagnosis/investigation_planner.py`, `diagnosis/investigation_engine.py`, `diagnosis/investigation_tools.py`, `diagnosis/meta_ai.py`

The diagnosis agent investigates the incident rather than merely generating a response from a single prompt.

### 14.1 Initial investigation

The agent receives:
- A validated incident record.
- The verification report.
- A validated evidence package.
- The available investigation tools.
- The supported diagnostic capabilities.

It then develops an initial investigation plan.

### 14.2 Investigation loop

The conceptual loop is:

```text
Receive Incident
      |
      v
Validate Evidence
      |
      v
Identify Known Facts
      |
      v
Generate Candidate Explanations
      |
      v
Select Next Investigation Step
      |
      v
Validate Proposed Tool and Arguments
      |
      v
Execute Approved Diagnostic Tool
      |
      v
Collect New Evidence
      |
      v
Evaluate the New Evidence
      |
      +---- Evidence insufficient and
      |     further investigation useful?
      |             |
      |             +---- Yes ----> Replan
      |             |
      |             +---- No
      v
Validate Findings
      |
      v
Produce Structured Diagnosis
```

### 14.3 Adaptive investigation

The agent should select further checks based on the evidence already collected.

For example, suppose the initial evidence establishes that the active reward scale is 25 instead of 100.

The agent might propose:
1. Inspect the active reward configuration.
2. Compare the active configuration with the declared configuration.
3. Inspect the reward implementation.
4. Check whether the relevant environment version matches the expected version.
5. Determine whether additional execution evidence is needed.

The investigation tools must only perform operations explicitly supported by their registered interfaces.

The agent must not execute arbitrary code, change environment configuration, delete artifacts, or initiate recovery.

### 14.4 Bounded autonomy

The agent should have:
- A maximum investigation-step budget.
- A maximum number of model calls.
- Timeouts.
- Per-tool execution limits.
- Input and output size limits.
- Defined stop conditions.
- Explicit handling for provider failures.

The agent should stop when:
- The evidence supports a sufficiently specific finding.
- Additional investigation is unlikely to provide useful information.
- Required evidence is unavailable.
- A safety restriction prevents further action.
- A resource limit is reached.

A stopped investigation must report whether it completed successfully or remained incomplete.

---

## 15. Meta AI Integration

> **Implementation status:** there is no `diagnosis/meta_ai.py`. The single provider adapter is `backend/ai/` (`MetaClient` + `AIService`, configured from `MODAL_API_KEY` and `META_*`; Meta Model API is the only hosted AI provider). The verification workflow's advisory investigator is `backend/verification/llm/ai_investigator.py`, a thin adapter over `AIService`.

**File:** `diagnosis/meta_ai.py`

The Meta AI provider adapter isolates model-specific integration from the rest of the system.

### Responsibilities

- Provider configuration.
- Authentication.
- Request construction.
- Response parsing.
- Timeouts and appropriate retry behaviour.
- Error normalization.
- Structured output validation.
- Safe logging.

The selected Meta AI model, endpoint, and authentication method must be confirmed before implementation. Do not assume that every Meta AI model is available through a public API.

Credentials must be supplied through an approved configuration mechanism and must not be committed or included in persisted evidence packages.

### AI responsibilities

The AI agent may:
- Interpret ambiguous intent.
- Propose verification workflows.
- Suggest additional diagnostic checks.
- Generate candidate explanations.
- Prioritize evidence collection.
- Explain relationships between observed findings.
- Identify missing information.
- Recommend next steps.

The AI must not:
- Override a deterministic result without additional evidence.
- Turn an anomaly score into a confirmed fault.
- Invent missing configuration or logs.
- Treat untrusted log content as privileged instructions.
- Claim that a recovery action occurred when it did not.
- Execute arbitrary code or shell commands.

---

## 16. Diagnosis Validation

**File:** `diagnosis/diagnosis_validator.py`

Every diagnosis must be validated before being returned or persisted as a completed investigation.

### Validation requirements

- Verify the response schema.
- Verify that the incident reference is correct.
- Check that supporting evidence references correspond to the investigation record.
- Distinguish observed facts from model-generated hypotheses.
- Record alternative explanations where appropriate.
- Record missing evidence.
- Ensure recommendations are within the supported tool and action boundaries.
- Reject malformed output.
- Mark the investigation incomplete when the available evidence does not support a useful conclusion.

### Confidence handling

The system may retain a model-provided confidence field if the selected provider supplies one, but it must not treat that field as a calibrated probability without separate validation.

The architecture should rely on:
- Evidence references.
- Deterministic verification outcomes.
- Reproducible checks.
- Explicit uncertainty.
- Validation of the proposed explanation.

A single confidence score must never be the sole basis for declaring a fault confirmed.

---

## 17. Safe Persistence and Data Handoff

**Files:** `verification/storage.py`, `diagnosis/storage.py`

The system generates data that will be consumed by Person 4. That data must remain structured, traceable, and safely stored.

### Data to persist

Verification storage may retain:
- Verification run identifiers.
- Normalized requirement references.
- Workflow plans and step results.
- Check outcomes.
- Evidence references.
- Verification reports.

Diagnosis storage may retain:
- Incident records.
- Evidence package references.
- Investigation plans.
- Completed investigation steps.
- Tool execution results.
- Diagnosis reports.
- Investigation status and timestamps.

### Storage requirements

- Validate records before persistence.
- Use stable identifiers and versioned record formats.
- Avoid silent overwrites.
- Handle interrupted writes.
- Detect malformed persisted data.
- Preserve the relationship between a run, incident, verification report, and diagnosis.
- Avoid persisting unnecessary secrets or sensitive data.
- Handle duplicate submissions according to a defined policy.
- Preserve completed records if a later investigation fails.

### Storage restrictions

All new storage code must remain inside `backend/verification/` or `backend/diagnosis/`.

Do not modify the shared database infrastructure or introduce a third backend folder.

Use an existing storage interface if it can be consumed without modifying files outside the permitted directories. Otherwise, document and implement an isolated persistence mechanism within the permitted scope.

### Handoff to Person 4

The final handoff should contain, as applicable:

- Incident identifier.
- Run and environment references.
- Verification report.
- Evidence package reference or payload.
- Diagnosis findings.
- Supporting evidence references.
- Alternative explanations.
- Missing evidence.
- Recommended further checks.
- Investigation status.
- Data schema version.

The handoff must be independently understandable and must not depend on access to in-memory objects that disappear when the process ends.

Person 4 remains responsible for artifact impact analysis, recovery planning, recovery execution, and evaluation.

---

## 18. Testing Architecture

Tests must verify the subsystem's behaviour, not merely confirm that functions return successfully.

All new tests and testing utilities must remain inside the two permitted directories. If the repository already has an external test runner or test suite, use it without modifying files outside those directories.

### 18.1 Input and extensibility tests

Test:
- Minimal valid input.
- Full input.
- Missing optional fields.
- Explicit null values.
- Malformed known fields.
- Unknown future fields.
- Different configuration shapes.
- Conflicting intent and configuration.
- Invalid schema versions.

Verify that adding an unrelated optional field does not break previously valid inputs.

### 18.2 Verification tests

Test:
- Matching expected and observed configuration.
- Mismatched configuration.
- Missing evidence.
- Invalid numeric values.
- Contradictory requirements.
- Multiple independent checks.
- Aggregate status calculation.
- Blocked checks.
- Internal check errors.
- Deterministic repeatability.

### 18.3 ML/DL tests

Test:
- Normal behaviour.
- Controlled anomalies.
- Insufficient observations.
- Stochastic variation.
- Missing features.
- Invalid feature values.
- Detector failure.
- Comparison against a baseline where appropriate.

Evaluate false-positive and false-negative behaviour where labelled or controlled scenarios are available.

### 18.4 AI-agent tests

Use a mocked Meta AI provider to test:
- Intent interpretation.
- Workflow planning.
- Tool selection.
- Invalid tool arguments.
- Replanning after new evidence.
- Missing evidence.
- Contradictory evidence.
- Malformed model responses.
- Provider timeouts.
- Investigation-budget exhaustion.
- Stop conditions.
- Untrusted instructions embedded in logs.

### 18.5 Persistence tests

Test:
- Save and reload.
- Duplicate records.
- Interrupted writes.
- Invalid persisted records.
- Version compatibility.
- Referential consistency.
- Preservation of completed records after a subsequent failure.

### 18.6 End-to-end tests

The complete test scenario should:

1. Receive developer intent and structured environment configuration.
2. Receive actual execution evidence.
3. Normalize the input.
4. Generate explicit requirements.
5. Plan and execute verification checks.
6. Identify a controlled discrepancy.
7. Construct an evidence package.
8. Conduct a bounded diagnosis using a mocked AI provider.
9. Validate the diagnosis.
10. Persist the generated records.
11. Reload the records.
12. Produce a structured handoff package.
13. Confirm that the handoff contains the necessary references and data.
14. Confirm that the implementation has not modified files outside the two permitted directories.

The controlled reward-scaling fault should be the initial canonical demonstration.

A separate test must establish that low reward alone does not automatically prove an environment defect.

### Testing policy

- Ordinary unit tests must not require live Meta AI credentials.
- External provider tests must be explicitly designated as integration tests.
- Do not claim that a test passed unless it was actually executed.
- Record environmental blockers and untested behaviour.
- Do not modify unrelated files to make tests pass.

---

## 19. Reliability, Observability, and Failure Recovery

The subsystem must remain understandable when individual components fail.

Record, where appropriate:
- Verification run identifier.
- Incident identifier.
- Workflow step identifier.
- Component name.
- Operation status.
- Evidence references.
- Failure category.
- Timestamp.
- Retry or termination reason.

Logs must not expose API credentials or unnecessarily repeat sensitive evidence.

The system should distinguish:
- Invalid input.
- Missing evidence.
- Unsupported requirements.
- Verification failure.
- Anomaly detection failure.
- Meta AI provider failure.
- Invalid diagnosis output.
- Persistence failure.

A failure in one optional anomaly detector should not silently invalidate unrelated deterministic checks.

A provider failure should not erase an already completed verification report.

A persistence failure must be reported rather than pretending the result was saved successfully.

---

## 20. Implementation Sequence

Implement the system in this order:

1. Inspect existing code inside the two permitted folders.
2. Define stable internal models and extensibility rules.
3. Implement the input adapter.
4. Implement intent parsing and context construction.
5. Implement the requirement registry.
6. Implement deterministic rules and checks.
7. Implement the workflow planner.
8. Implement the verification engine and validator.
9. Add an initial anomaly-detector interface and a simple evaluated baseline method.
10. Implement incident detection and classification.
11. Implement evidence construction and validation.
12. Confirm the Meta AI provider.
13. Implement the provider adapter and investigation prompts.
14. Implement the bounded investigation planner and engine.
15. Implement diagnosis validation and reporting.
16. Implement safe persistence.
17. Add unit and integration tests.
18. Test the controlled reward-scaling scenario.
19. Test the handoff to a mock Person 4 consumer.
20. Review all changes to confirm the strict folder boundary was respected.

Do not build every possible feature before producing a working end-to-end workflow.

The first milestone should demonstrate the complete flow with deterministic checks, a controlled fault, mocked AI diagnosis, and validated evidence persistence. Additional ML/DL methods and investigation tools can then be added behind stable interfaces.

---

## 21. Definition of Done

The subsystem is ready for integration when:

- It accepts developer intent and extensible structured input.
- It incorporates actual environment and agent configuration.
- It transforms intent into traceable requirements.
- It plans and executes a verification workflow.
- It combines deterministic rules with optional ML/DL anomaly detection.
- It identifies discrepancies without confusing anomalies with confirmed faults.
- It builds validated evidence packages.
- It performs bounded, adaptive AI investigations.
- It validates the final diagnosis.
- It distinguishes facts, hypotheses, recommendations, and missing evidence.
- It safely persists generated records.
- It produces a complete handoff package for Person 4.
- Unit and integration tests cover normal and faulty behaviour.
- The controlled reward-scaling scenario is demonstrated successfully.
- Additional input fields can be introduced without breaking supported inputs.
- No files outside `backend/verification/` and `backend/diagnosis/` have been modified by Person 3.
- Documentation identifies assumptions, limitations, dependencies, and unresolved integration requirements.

---

## 22. Git and Collaboration

Follow the repository's `AGENTS.md` and `opencode.md`.

- Work on `backend3`.
- Inspect the current branch and working tree before editing.
- Make small, meaningful commits at logical milestones.
- Keep commit messages to one line.
- Push development changes only to `backend3`.
- Create or update pull requests from `backend3` to `main`.
- Never commit directly to, push directly to, or merge into `main` without explicit authorization.
- Do not overwrite other contributors' work.
- Do not modify files outside the two permitted directories.
- Coordinate external interface requirements rather than implementing changes outside your ownership.
- Run relevant tests before committing.
- Review the diff before pushing.
- Report actual test results, failures, assumptions, and remaining integration dependencies accurately.

Example commit:

`feat: add adaptive verification workflow planner`

---

## 23. Final Architectural Principle

Person 3's system must function as a bounded, independent verification and diagnosis agent.

It must understand the developer's intent, use available configuration and execution evidence, plan and execute appropriate checks, adapt its investigation when new evidence appears, validate its conclusions, and safely preserve the results.

**Rule-based verification provides deterministic checks. ML/DL provides evaluated anomaly signals. Meta AI provides flexible reasoning and adaptive investigation. Validation and evidence provenance keep the combined system accountable.**

The resulting evidence and diagnosis are handed to Person 4, who remains responsible for determining the impact on training artifacts and carrying out validated recovery.

The system should be extensible enough to support new environment types, agent algorithms, metrics, logs, variables, and diagnostic tools without requiring a rewrite of the core verification and diagnosis engines.