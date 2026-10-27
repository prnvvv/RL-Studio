# Person 4 — Provenance, Artifact Impact, Recovery, Evaluation & Persistence Agent Instructions

> Read the repository-root `AGENTS.md` first. This file governs Person 4's detailed ownership. Recovery is a controlled, auditable operation: unknown compatibility or incomplete evidence must not be silently treated as safe.

## 1. Role and mission

You own the data/persistence foundation and the modules that trace training lineage, assess potential impact, execute supported recovery operations, and evaluate the outcome.

The purpose is not to claim that every artifact touched by a fault is certainly corrupted. The purpose is to reconstruct evidence-backed exposure, identify uncertainty, plan a compatible recovery, and measure whether the recovered policy performs acceptably.

## 2. Ownership

Primary ownership:
- `backend/database/`
- `backend/provenance/`
- `backend/recovery/`
- `backend/evaluation/`
- shared database migrations and persistence configuration

You do not own the PPO training loop (Person 2), runtime verification/AI client (Person 3), or frontend (Person 1). You define persistence interfaces and artifact/recovery schemas in coordination with all owners.

## 3. First steps
1. Read root `AGENTS.md` and inspect existing database conventions.
2. Confirm current DB choice and migration tooling; do not assume PostgreSQL or a particular ORM is already installed.
3. Agree on canonical run/event/checkpoint/incident schemas with Persons 2 and 3.
4. Agree on API response needs with Person 1.
5. Establish the initial schema and migration policy before parallel persistence work grows.
6. Document what lineage granularity the MVP can actually capture.

## 4. Persistence infrastructure

### 4.1 Database and migrations
Use the project's existing database/ORM/migration stack. If none exists and the team has agreed on PostgreSQL, a reasonable stack is SQLAlchemy plus Alembic with Pydantic at API boundaries. Do not independently add a second ORM or a second database.

Create a central, configurable database session/connection lifecycle. Avoid creating a new engine for each request. Use transaction boundaries and rollback on failure. Do not keep a DB transaction open during long-running training, model inference, or recovery operations.

### 4.2 Schema ownership
Own shared migrations and base persistence infrastructure. Module owners remain responsible for their own service/repository behavior. Agree with each owner before changing their tables or field semantics.

Likely entities:
- project
- experiment
- environment version/config fingerprint
- agent configuration/fingerprint
- training run
- event index or event references
- episode/rollout/training update association
- checkpoint/artifact
- requirement/incident references
- diagnosis reference
- recovery attempt/action
- evaluation run/result
- audit event

Avoid storing every high-frequency event as a separate relational row if it overwhelms the MVP. Choose a documented storage strategy that preserves required evidence and supports querying by run/time/artifact. Keep the authoritative record and any aggregation policy explicit.

### 4.3 Migration safety
- Every schema change has a migration and rollback/forward-repair plan where feasible.
- Never edit an already-applied shared migration in place without explicit team agreement and environment reset plan.
- Do not run destructive migrations against user data without a backup and approval.
- Test migrations from an empty DB and from the current supported schema.
- Keep test DB isolation reliable.
- Avoid multiple people editing the same migration file simultaneously.

## 5. Provenance model

### 5.1 Required associations
Track relationships among:
- project/experiment/run
- immutable environment version
- agent configuration
- episode and rollout
- training update
- checkpoint
- fault injection interval
- execution events
- incident
- recovery attempt
- evaluation run

The required granularity must be agreed with Person 2. If the trainer cannot identify the exact rollouts consumed by a training update, record the coarser association and mark it as a limitation; do not invent precise lineage.

### 5.2 Artifact registry
Each artifact record should contain:
- stable artifact/checkpoint ID
- type
- immutable storage reference/path or object key
- content hash
- creation time
- run/environment/agent fingerprints
- timestep/update/episode counters
- metadata schema version
- integrity/validation status
- relevant state components included
- parent/source checkpoint when applicable

Never use a display filename as the sole identity. Validate that referenced files remain within the allowed artifact root. Avoid arbitrary path reads and path traversal.

### 5.3 Exposure analysis
Given a fault interval and affected environment version:
1. Identify runs and events inside the interval/version.
2. Find episodes/rollouts generated under the affected conditions.
3. Find training updates that consumed those experiences, to the extent recorded.
4. Find checkpoints containing those updates.
5. Classify exposure and lineage completeness.
6. Return a traceable explanation with source records.

Use explicit classes such as:
- `confirmed_exposed`
- `potentially_affected`
- `not_exposed_based_on_recorded_lineage`
- `unknown_incomplete_lineage`

Exposure does not prove causal damage. The output should distinguish “artifact included experience from a faulty environment” from “artifact performance was causally degraded by the fault.”

### 5.4 Missing or conflicting lineage
- Missing records must produce `unknown` or `incomplete`.
- Conflicting timestamps or versions must be surfaced.
- Do not assume event arrival order equals execution order.
- Prefer explicit sequence numbers and artifact associations.
- Never silently label an artifact unaffected because no event was found.
- Record the reason and evidence behind every classification.

## 6. Recovery planning

### 6.1 Supported actions
Implement a small allow-list for the MVP:
- validate/correct a supported environment configuration through an approved configuration operation
- select and restore a compatible checkpoint
- discard incompatible pending on-policy rollouts
- continue training with fresh experience
- run post-recovery evaluation

Do not execute arbitrary code, shell commands, or LLM-produced scripts. Do not automatically rewrite source files.

### 6.2 Recovery plan contents
A plan should include:
- recovery and incident IDs
- reason for the selected strategy
- source checkpoint and its hash
- target environment/agent configuration fingerprint
- lineage evidence and uncertainty
- compatibility checks
- state components required for continuation
- steps to execute, in order
- expected preconditions
- rollback/failure behavior
- evaluation criteria
- human approval requirement, if applicable

Persist a plan before executing it. Keep proposed, approved, executing, completed, failed, blocked, and evaluated states distinct.

### 6.3 Checkpoint compatibility
Before restoration, validate:
- artifact exists and is readable
- content hash/integrity matches
- algorithm and policy architecture match
- expected observation/action spaces match
- environment/configuration compatibility is understood
- library/model serialization compatibility is acceptable
- normalization state is available if used
- optimizer/training/RNG/counters are present when required by the supported continuation semantics
- checkpoint predates or otherwise avoids the affected training updates according to the recovery policy
- artifact has not been deleted or superseded

If any required check fails, block recovery and explain the exact reason. Do not restore “the latest checkpoint” by default. The latest checkpoint may include affected updates.

### 6.4 PPO-specific considerations
PPO is on-policy. Pending rollout data collected under a faulty environment or incompatible policy/environment state should not be reused unless a rigorously defined policy says it is valid. The normal MVP recovery is to restore a compatible pre-impact checkpoint, correct the environment, discard incompatible pending experience, and collect fresh experience.

Do not assume saving only the policy weights fully restores a training state. Coordinate with Person 2 on optimizer, scheduler (if any), normalization, random-number-generator state, timestep counters, and rollout buffer semantics. If full state cannot be restored, disclose that the operation is a warm start rather than a faithful continuation.

### 6.5 Execution controls
- Require a valid plan and completed preflight.
- Make operations idempotent or protect them with a recovery operation ID.
- Use a lock/lease to prevent concurrent restores of the same run/artifact.
- Preserve original checkpoints; never overwrite the only source artifact.
- Record each action and result in the audit log.
- Apply bounded timeouts and cancellation behavior.
- Validate postconditions after each step.
- On partial failure, stop and mark the recovery as failed/blocked; do not pretend rollback occurred if it did not.
- Do not launch evaluation until the recovered artifact is valid and the target environment is healthy.

## 7. Evaluation engine

### 7.1 Baselines
Where feasible, compare:
- healthy baseline agent/checkpoint
- faulty agent/checkpoint
- recovered agent/checkpoint

All comparisons must identify the exact artifact and evaluation environment version. A baseline is not meaningful if it was evaluated under different conditions without explanation.

### 7.2 Metrics
Implement metrics relevant to warehouse navigation:
- task success rate
- mean/median episode reward
- episode length
- collision rate
- timeout/failure rate
- recovery duration
- evaluation throughput if useful

Define each metric's denominator, episode handling, and missing-data policy. Do not confuse training reward with held-out evaluation reward.

### 7.3 Protocol
- Use an explicit evaluation configuration and a documented number of episodes.
- Use fixed seeds for repeatable comparisons when practical.
- Use multiple seeds where budget permits.
- Keep evaluation environment healthy and immutable during the comparison.
- Avoid training updates during evaluation.
- Separate evaluation RNG/state from training RNG/state.
- Report uncertainty/variation where computed.
- Record failed evaluation episodes and infrastructure errors.
- Never hard-code a successful result.

### 7.4 Recovery acceptance
Define acceptance criteria with the team. A possible criterion is that the recovered agent satisfies a minimum success rate and improves over the faulty agent without unacceptable regression against a healthy baseline. Do not invent thresholds after seeing the result; configure them in advance or clearly label them exploratory.

Possible statuses:
- `passed`
- `failed`
- `inconclusive`
- `not_run`
- `blocked`

Recovery execution completion is not the same as recovery success. Success is a conclusion from the configured evaluation policy.

## 8. Audit trail
Record append-only or versioned audit entries for:
- impact-analysis runs
- artifact classifications and evidence
- recovery plan creation/approval
- preflight validation
- recovery steps and outcomes
- checkpoint restore details
- evaluation configuration/results
- operator or system identity where applicable
- timestamps, correlation IDs, and schema versions

Do not erase previous failed attempts or rewrite the original incident to make the history look successful. Corrections should be new audit entries.

## 9. API/service boundaries
Expose services through the existing API architecture; coordinate route registration with the API owner. Suggested operation groups:
- artifact/checkpoint metadata
- provenance trace/impact analysis
- recovery plan preview
- recovery validation/preflight
- recovery execution/status
- evaluation start/status/results
- audit history

Never put long recovery or evaluation jobs inside a blocking HTTP request. Return a job/recovery/evaluation ID and expose status polling/live updates through the agreed mechanism. Enforce authorization and idempotency where required.

## 10. Error handling and operational resilience
Handle:
- missing checkpoint
- corrupted checkpoint/hash mismatch
- incompatible algorithm/configuration
- missing lineage
- database unavailable
- transaction conflict
- disk full/permission failure
- interrupted recovery
- worker crash
- partial restore
- evaluation environment failure
- timeout/cancellation
- incomplete evaluation results

Each failure should have a stable category, safe message, detailed internal diagnostic, and final state. Never convert missing evidence into an empty list that means “no impact” unless the contract explicitly distinguishes missing from none.

## 11. Security
- Keep artifacts inside an approved storage root.
- Resolve and validate paths to prevent traversal.
- Do not load untrusted pickle/serialized artifacts.
- Restrict file permissions and artifact access.
- Do not allow model output to supply an executable path or shell command.
- Avoid exposing local filesystem paths to the frontend.
- Use atomic file operations and integrity hashes.
- Do not log secrets or full sensitive payloads.
- Recovery endpoints need strict validation and appropriate authorization.
- Destructive cleanup must be explicit, scoped, and auditable.

## 12. Testing requirements
- database migrations from empty/current schema
- repository transaction and rollback behavior
- artifact registration and integrity hashes
- path traversal and missing file handling
- provenance chain construction
- fault interval boundary tests
- missing/conflicting lineage produces unknown
- exposure classification semantics
- checkpoint compatibility matrix
- incompatible checkpoint blocks recovery
- recovery idempotency and concurrent-operation locking
- partial failure and cancellation handling
- PPO pending rollout discard/fresh experience path
- evaluation metric calculations and denominators
- fixed-seed evaluation reproducibility
- baseline comparison and inconclusive results
- audit trail immutability/append behavior
- end-to-end recovery with real artifacts in a small test run

Ordinary CI should use tiny local fixtures and not require a live Meta AI API. Do not use arbitrary untrusted model checkpoints in tests.

## 13. Definition of done
A feature is complete when artifact lineage is traceable to the granularity actually recorded, uncertainty is explicit, recovery is preflighted and auditable, incompatible states are blocked, evaluation uses comparable baselines, migrations are safe, and tests cover both successful and failed paths.
