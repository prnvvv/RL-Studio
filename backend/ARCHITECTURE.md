# RL Studio — Environment and Training Architecture

## 1. Purpose

This document defines Person 2's architecture for environment execution, RL training, execution monitoring, fault injection, and checkpoint production.

The system must run RL experiments and produce structured evidence that downstream components can inspect without independently reconstructing the training process.

## 2. Architectural Responsibilities

Person 2's subsystem owns five main responsibilities:

1. **Environment management:** Create and configure the RL environment.
2. **Training execution:** Configure, start, control, and stop training runs.
3. **Execution monitoring:** Collect metrics, rewards, episodes, events, logs, and traces.
4. **Fault injection:** Introduce controlled, documented faults for testing.
5. **Checkpoint production:** Save supported training checkpoints and their metadata.

The subsystem must expose stable interfaces for accessing these records.

## 3. Proposed Directory Structure

Adapt this structure to the existing repository. Reuse existing modules and do not create duplicate implementations.

```text
backend/
└── [Person 2 assigned directory]/
    ├── __init__.py
    ├── models.py
    ├── interfaces.py
    ├── exceptions.py
    │
    ├── environments/
    │   ├── __init__.py
    │   ├── environment_factory.py
    │   ├── environment_registry.py
    │   └── environment_manager.py
    │
    ├── agents/
    │   ├── __init__.py
    │   ├── agent_loader.py
    │   ├── template_registry.py
    │   └── configuration.py
    │
    ├── training/
    │   ├── __init__.py
    │   ├── training_manager.py
    │   ├── run_controller.py
    │   └── lifecycle.py
    │
    ├── monitoring/
    │   ├── __init__.py
    │   ├── metrics_collector.py
    │   ├── reward_tracker.py
    │   ├── episode_tracker.py
    │   ├── event_collector.py
    │   ├── log_collector.py
    │   └── trace_collector.py
    │
    ├── fault_injection/
    │   ├── __init__.py
    │   ├── fault_models.py
    │   ├── fault_registry.py
    │   └── fault_controller.py
    │
    ├── checkpoints/
    │   ├── __init__.py
    │   ├── checkpoint_manager.py
    │   └── checkpoint_metadata.py
    │
    ├── storage/
    │   ├── __init__.py
    │   └── execution_store.py
    │
    ├── api/
    │   ├── __init__.py
    │   ├── run_routes.py
    │   ├── metrics_routes.py
    │   ├── evidence_routes.py
    │   └── fault_routes.py
    │
    └── tests/
        ├── test_environments.py
        ├── test_training_lifecycle.py
        ├── test_monitoring.py
        ├── test_fault_injection.py
        ├── test_checkpoints.py
        └── test_execution_api.py
```

The names above are proposed logical modules, not a requirement to recreate files that already exist.

## 4. Component Design

### 4.1 Environment Management

The environment subsystem creates and configures supported RL environments.

It must record the environment identity, version, configuration, supported observation/action spaces, and relevant initialization details.

It must not assume that every environment uses the same configuration schema.

### 4.2 Agent and Configuration Management

The agent subsystem loads supported agents or templates and validates their configuration.

It preserves the effective configuration used for each run, including relevant hyperparameters and algorithm settings.

Agent definitions and configuration snapshots must be distinguishable from the live state of a running experiment.

### 4.3 Training Lifecycle

The training manager creates and controls individual runs.

Each run has a stable `run_id` and an explicit lifecycle state. Run transitions and failures must be recorded.

Where supported, the run is associated with the agent, environment, configuration snapshots, seed, training algorithm, and software versions.

Training execution must be isolated sufficiently to prevent unrelated runs from corrupting one another's records.

### 4.4 Monitoring

Monitoring collects observations as training progresses.

Supported observation categories include:

- Rewards.
- Episode lengths and outcomes.
- Timesteps.
- Success rate, where defined.
- Training metrics.
- Lifecycle and environment events.
- Logs.
- Traces.
- Termination reasons.

Each observation must retain its timestamp and run association. Episode- and timestep-level identifiers should be included where available.

Missing observations must remain missing rather than being replaced with fabricated values.

### 4.5 Fault Injection

Fault injection introduces explicitly requested, controlled faults.

Every injection must have a stable identifier and be associated with the affected run and component.

The subsystem records the intended fault, configured parameters, injection result, and observed evidence.

The canonical demonstration may use a reward-scale discrepancy between an expected configuration value of `100` and an actual value of `25`. The subsystem must record these as distinct, attributable values.

Fault injection must be reproducible where possible, isolated from ordinary runs, and safe to stop.

### 4.6 Checkpoint Management

Checkpoint management saves supported training state and records metadata.

Checkpoint records should include a checkpoint ID, run ID, creation time, timestep, policy version, environment version, and artifact location where available.

Checkpoint creation and checkpoint validity are different states. The subsystem must not claim integrity or recoverability without the relevant checks.

### 4.7 Persistence

Persistence stores run metadata, configuration snapshots, observations, events, fault records, and checkpoint metadata.

Use the repository's existing persistence infrastructure. Avoid introducing a separate database solely for this subsystem.

Records must remain queryable by stable IDs, with relationships preserved between runs and their evidence.

### 4.8 API Layer

The API layer exposes run control and evidence retrieval.

Use the established framework, route conventions, authentication, and error-handling mechanisms.

Keep large evidence collections paginated and bounded. Return structured data rather than requiring clients to parse arbitrary log text.

## 5. Data Flow

```text
Agent Template + Agent Configuration
                  +
Environment Configuration
                  +
Training Configuration
                  |
                  v
           Create Training Run
                  |
                  v
       Validate and Snapshot Inputs
                  |
                  v
        Initialise Environment
                  |
                  v
          Execute RL Training
                  |
                  +----------------------+
                  |                      |
                  v                      v
          Collect Metrics         Capture Events
                  |                Logs and Traces
                  |                      |
                  +-----------+----------+
                              |
                              v
                  Persist Execution Evidence
                              |
                 +------------+------------+
                 |                         |
                 v                         v
          Save Checkpoints          Record Faults
                 |                         |
                 +------------+------------+
                              |
                              v
                    Expose Run and Evidence
```

The monitoring and persistence components should capture evidence throughout execution, not only after training finishes.

## 6. Shared Execution Record

Every run should expose a consistent record containing the applicable fields:

```text
run_id
agent_id
agent_type
agent_template
agent_config
environment_id
environment_version
environment_config
training_config
algorithm
hyperparameters
seed
training_status
started_at
completed_at
current_timestep
total_timesteps
total_episodes
```

Fields should remain optional when the value is genuinely unavailable or inapplicable. Record schema versions where needed.

## 7. Evidence Model

### Metrics

```text
metric_name
metric_value
metric_unit
run_id
episode_id
timestep
timestamp
```

### Episodes

```text
episode_id
run_id
episode_length
episode_reward
termination_reason
started_at
completed_at
```

### Events

```text
event_id
run_id
event_type
event_data
timestamp
```

### Logs and Traces

```text
log_id
run_id
log_level
log_message
timestamp
trace_id
trace_data
```

### Fault Injection

```text
fault_id
run_id
fault_type
fault_config
fault_status
injection_timestamp
expected_effect
observed_effect
```

### Checkpoints

```text
checkpoint_id
run_id
checkpoint_path
policy_version
environment_version
timestep
created_at
```

These are logical data contracts. Align them with the repository's actual models and agreed integration schemas before implementation.

## 8. Integration Requirements

The subsystem must provide Person 3 with:

- Agent and environment configuration snapshots.
- Developer-independent run identifiers.
- Environment and training metadata.
- Time-ordered execution metrics and rewards.
- Episode records and termination reasons.
- Events, logs, and traces.
- Fault-injection records.
- Checkpoint references.
- Missing-data and collection-error indicators.

Person 3 is responsible for interpreting developer intent and performing intent-to-execution verification. Person 2 provides the underlying execution facts.

The subsystem must provide Person 4 with:

- Run and environment versions.
- Checkpoint metadata and artifact references.
- Policy-version associations.
- Available trajectory or experience identifiers.
- Links between training steps and created artifacts, where supported.
- Evidence required to trace the origin of training artifacts.

Person 4 owns downstream artifact impact analysis, recovery, and recovery evaluation.

Do not duplicate either downstream subsystem.

## 9. Reliability Requirements

- Validate incoming configuration.
- Keep run identifiers stable.
- Record state transitions.
- Handle training failures explicitly.
- Preserve timestamps and provenance references.
- Distinguish missing evidence from zero-valued observations.
- Avoid unbounded in-memory accumulation of logs or metrics.
- Use bounded API queries.
- Record fault injection before, during, and after execution as appropriate.
- Prevent fault injection without explicit authorisation.
- Avoid exposing secrets in logs.
- Use controlled shutdown and cleanup.
- Report limitations in reproducibility honestly.

## 10. Initial End-to-End Demonstration

The initial demonstration should:

1. Create a supported RL environment.
2. Load an agent configuration.
3. Create and start a training run.
4. Collect rewards, episodes, and metrics.
5. Record events and logs.
6. Trigger a controlled reward-scale configuration mismatch.
7. Preserve the expected and actual configuration values.
8. Collect evidence associated with the affected run.
9. Save and reference available checkpoints.
10. Expose the run and evidence through the agreed interfaces.

The demonstration must produce real execution records. It must not manufacture metrics or claim a fault was detected by another component when only the execution evidence has been produced.

## 11. Definition of Done

Person 2's subsystem is ready for integration when environment execution, training lifecycle, monitoring, fault injection, persistence, and checkpoint metadata work together and expose stable, documented contracts.

All relevant tests must be executed, and remaining limitations must be documented.