# RL Studio — Person 2 Implementation Plan

## Objective

Build the environment and training subsystem that executes RL runs, records complete execution evidence, supports controlled fault injection, and exposes stable interfaces for downstream verification and recovery.

## Phase 1 — Repository Inspection

- [ ] Read the root and backend `AGENTS.md` instructions.
- [ ] Inspect the existing backend directory structure.
- [ ] Identify the current environment and training implementations.
- [ ] Identify existing API routes, models, database models, and persistence utilities.
- [ ] Identify the RL libraries and supported algorithms already used by the project.
- [ ] Identify the current run, environment, and checkpoint identifiers.
- [ ] Review Person 3 and Person 4 integration contracts without modifying their files.
- [ ] Confirm the exact directory and files assigned to Person 2.
- [ ] Record existing functionality that can be reused.

## Phase 2 — Shared Execution Models

- [ ] Define or reuse the training-run model.
- [ ] Define or reuse agent and environment configuration models.
- [ ] Define or reuse training configuration models.
- [ ] Define or reuse lifecycle status values.
- [ ] Define metric observation models.
- [ ] Define episode result models.
- [ ] Define structured event and log models.
- [ ] Define fault-injection record models.
- [ ] Define checkpoint metadata models.
- [ ] Establish stable identifiers and timestamp conventions.
- [ ] Support optional and extensible configuration fields.
- [ ] Confirm shared schemas with affected contributors before changing integration contracts.

## Phase 3 — Environment Management

- [ ] Implement or improve environment creation.
- [ ] Implement environment configuration validation.
- [ ] Record environment identity and version.
- [ ] Record effective environment configuration.
- [ ] Handle unsupported environments and invalid configurations.
- [ ] Test environment initialization and cleanup.
- [ ] Verify that environment failures are reported explicitly.

## Phase 4 — Agent and Configuration Management

- [ ] Implement or improve agent loading.
- [ ] Support the project's existing predefined agent templates.
- [ ] Validate agent configuration and hyperparameters.
- [ ] Record the effective agent configuration for each run.
- [ ] Record the selected training algorithm.
- [ ] Record random seeds where supported.
- [ ] Preserve configuration snapshots or immutable references.
- [ ] Test invalid and unsupported configurations.

## Phase 5 — Training Lifecycle

- [ ] Implement training-run creation.
- [ ] Assign stable run identifiers.
- [ ] Implement explicit lifecycle states.
- [ ] Implement training startup.
- [ ] Implement training status retrieval.
- [ ] Implement controlled stopping and cancellation.
- [ ] Record startup, completion, and failure timestamps.
- [ ] Handle runtime exceptions and interrupted runs.
- [ ] Prevent invalid lifecycle transitions.
- [ ] Test normal completion and failure paths.

## Phase 6 — Execution Monitoring

- [ ] Collect timestep-level or interval-level metrics as appropriate.
- [ ] Record episode rewards.
- [ ] Record episode lengths.
- [ ] Record termination reasons.
- [ ] Calculate supported aggregate reward metrics.
- [ ] Calculate success rates only where the environment defines success.
- [ ] Capture lifecycle and environment events.
- [ ] Capture structured logs.
- [ ] Capture relevant traces.
- [ ] Attach timestamps and run identifiers to observations.
- [ ] Associate episode and timestep identifiers where available.
- [ ] Handle missing observations without fabricating values.
- [ ] Ensure monitoring does not significantly disrupt training.
- [ ] Test metrics, events, logs, and traces independently.

## Phase 7 — Controlled Fault Injection

- [ ] Define supported fault types.
- [ ] Validate fault-injection configurations.
- [ ] Implement explicit fault-injection requests.
- [ ] Assign stable fault identifiers.
- [ ] Associate every fault with the relevant run.
- [ ] Record injection time and target component.
- [ ] Record the expected effect when defined.
- [ ] Record the actual observed effect.
- [ ] Prevent unintended fault injection into ordinary runs.
- [ ] Implement safe failure handling and cleanup.
- [ ] Implement the controlled reward-scale mismatch demonstration.
- [ ] Verify that expected and actual configuration values are recorded separately.
- [ ] Test successful, rejected, and failed injections.

## Phase 8 — Checkpoint Management

- [ ] Inspect the project's existing checkpoint implementation.
- [ ] Implement or improve checkpoint creation where supported.
- [ ] Assign stable checkpoint identifiers.
- [ ] Record the associated run.
- [ ] Record the timestep and policy version.
- [ ] Record environment version and configuration references.
- [ ] Record checkpoint location and creation time.
- [ ] Validate checkpoint integrity where supported.
- [ ] Handle incomplete checkpoint writes.
- [ ] Test checkpoint metadata and retrieval.
- [ ] Coordinate artifact provenance requirements with Person 4.

## Phase 9 — Persistence

- [ ] Reuse the project's existing database or persistence layer.
- [ ] Persist run metadata.
- [ ] Persist configuration snapshots or references.
- [ ] Persist metric observations.
- [ ] Persist episode results.
- [ ] Persist events, logs, and traces.
- [ ] Persist fault-injection records.
- [ ] Persist checkpoint metadata.
- [ ] Preserve relationships between runs and evidence.
- [ ] Implement bounded queries and pagination where needed.
- [ ] Handle duplicate identifiers and failed writes.
- [ ] Test save, retrieval, and error-handling paths.

## Phase 10 — API and Integration

- [ ] Inspect existing API route conventions.
- [ ] Implement or reuse run creation and retrieval endpoints.
- [ ] Implement or reuse run start, stop, and status endpoints.
- [ ] Expose metrics and rewards.
- [ ] Expose episode results.
- [ ] Expose events, logs, and traces.
- [ ] Expose environment and configuration information.
- [ ] Expose controlled fault-injection operations.
- [ ] Expose checkpoint metadata.
- [ ] Validate request and response schemas.
- [ ] Implement authentication and authorisation according to project conventions.
- [ ] Add pagination and limits for large evidence collections.
- [ ] Document actual endpoint paths and schemas.
- [ ] Confirm Person 3 can retrieve the evidence required for verification.
- [ ] Confirm Person 4 can retrieve the available provenance references.

## Phase 11 — Testing

- [ ] Test environment initialization and configuration.
- [ ] Test agent loading and configuration.
- [ ] Test training lifecycle transitions.
- [ ] Test reward and episode collection.
- [ ] Test metric aggregation.
- [ ] Test event and log capture.
- [ ] Test trace capture where supported.
- [ ] Test fault-injection behaviour.
- [ ] Test checkpoint creation and metadata.
- [ ] Test persistence and retrieval.
- [ ] Test invalid API requests.
- [ ] Test runtime failures and interrupted training.
- [ ] Test missing evidence handling.
- [ ] Test stable identifiers and timestamp ordering.
- [ ] Run relevant existing backend tests.
- [ ] Run available lint and type checks.
- [ ] Record the actual test results.

## Phase 12 — End-to-End Demonstration

- [ ] Create an RL environment.
- [ ] Configure and load an agent.
- [ ] Start a training run.
- [ ] Collect real training metrics and episode results.
- [ ] Capture events, logs, and relevant traces.
- [ ] Trigger the controlled reward-scale mismatch.
- [ ] Preserve expected and actual configuration values.
- [ ] Associate all evidence with the correct run.
- [ ] Save a checkpoint where supported.
- [ ] Verify that all available records can be retrieved.
- [ ] Confirm the evidence is usable by Person 3's verification system.
- [ ] Confirm artifact references are usable by Person 4.
- [ ] Document any remaining limitations.

## Phase 13 — Final Review

- [ ] Review the implementation against `AGENTS.md`.
- [ ] Review the implementation against `ARCHITECTURE.md`.
- [ ] Check for duplicate implementations.
- [ ] Check that no other contributor's files were modified.
- [ ] Review the final Git diff.
- [ ] Confirm the work remains on `dev3`.
- [ ] Document implemented functionality.
- [ ] Document tests actually executed and their results.
- [ ] Document outstanding issues and integration dependencies.

## Completion Criteria

Person 2's work is complete when the RL environment and training lifecycle produce reliable, traceable execution evidence; controlled faults are recorded accurately; checkpoints are referenced where supported; and downstream components can retrieve the required information through stable interfaces.

Do not mark a task complete merely because a file or endpoint has been created. Confirm that the functionality works and report any unverified behaviour.