# Self-Healing RL Studio — Repository-Wide Agent Instructions

> **Applies to every contributor, coding agent, reviewer, and automation working in this repository.**
> This file is the shared engineering contract. Person-specific `AGENTS.md` files add ownership-specific requirements; they do not override this file. If two instructions conflict, stop and resolve the conflict with the affected owners instead of silently choosing one.

## 1. Product mission and scope

Self-Healing RL Studio is a developer platform for finding, investigating, tracing, and safely recovering from faults in reinforcement-learning (RL) environments and training runs. The initial demonstrator is a reproducible 2D warehouse-navigation environment using PPO.

The core workflow is:

1. **Understand intent:** capture developer-confirmed requirements as explicit, versioned contracts.
2. **Execute and observe:** run a reproducible RL experiment and record evidence.
3. **Detect faults:** compare actual execution with confirmed expectations and supported invariants.
4. **Investigate:** use a Meta AI model, where access is configured, to analyze real evidence and suggest likely causes.
5. **Trace impact:** associate experiences, updates, checkpoints, and environment versions; state exposure and uncertainty honestly.
6. **Recover safely:** execute only supported, validated operations.
7. **Verify recovery:** evaluate against comparable baselines and report measured outcomes.

The platform must not claim universal RL-bug detection, prove causality from temporal association alone, or declare recovery successful before evaluation.

## 2. Source-of-truth and precedence

Read this file before changing code. Then read the most specific `AGENTS.md` that governs the files you will edit:
- `frontend/AGENTS.md` or `frontend/app/AGENTS.md` for Person 1's owned frontend files.
- `backend/AGENTS.md` and the relevant module-specific file for backend work.
- `shared/AGENTS.md` for shared schemas/contracts, if present.
- `tests/AGENTS.md` for shared integration/end-to-end tests, if present.
- `docs/AGENTS.md` for documentation, if present.

The root file governs all contributors. More specific instructions can add constraints but cannot weaken root security, data integrity, testing, or evidence requirements.

Before assuming a path exists, inspect the actual repository. Do not create duplicate modules just because a planned path is absent. If the repository differs from the proposed layout, preserve established conventions and document any necessary adjustment.

## 3. Product principles

- **Evidence before explanation.** Record raw observations and provenance before asking a model to interpret them.
- **Confirmed intent before hard claims.** Separate developer-confirmed rules from inferred hypotheses.
- **Deterministic checks for hard invariants.** Use AI to interpret evidence and prioritize hypotheses, not as the sole enforcer of safety-critical contracts.
- **Reproducibility.** Record seeds, versions, configurations, dependency versions, and artifact identifiers.
- **Fail closed for destructive operations.** Unknown compatibility, incomplete lineage, missing checkpoints, or uncertain target state must block automatic recovery.
- **Truthful UI.** Mark mock data, pending work, incomplete lineage, uncertain diagnosis, and unverified recovery clearly.
- **Small vertical slices.** Prioritize one complete, testable end-to-end scenario over many disconnected screens.
- **Least privilege.** Never execute arbitrary model-generated code or user-supplied code with unrestricted privileges.
- **Modular ownership.** A person owns a module's implementation; cross-module contracts are jointly agreed and versioned.

## 4. Initial MVP boundaries

Prioritize:
- One 2D warehouse-navigation environment.
- One supported training algorithm: PPO through Stable-Baselines3.
- A small, explicit set of controlled faults: reward scaling, selected observation corruption, and invalid termination.
- Developer-confirmed runtime contracts.
- Evidence-backed incident generation.
- Meta AI investigation behind a replaceable provider interface.
- Run/event/checkpoint lineage.
- A conservative checkpoint restore and fresh-experience workflow.
- Evaluation against healthy and faulty baselines.

Do not add arbitrary user code execution, multi-agent RL, distributed training, Kubernetes, many algorithms, automatic source-code rewriting, or broad claims of general repair unless the team explicitly changes scope.

CartPole may be used as a secondary smoke-test environment. Do not allow the secondary environment to delay the warehouse vertical slice.

## 5. Repository ownership

Ownership is a boundary, not a ban on collaboration. Changes to another owner's implementation require a review from that owner.

- **Person 1 — Frontend:** `frontend/`; dashboard, forms, visualizations, API client, UI tests.
- **Person 2 — RL engine:** `backend/environments/`, `backend/training/`, `backend/monitoring/`, `backend/fault_injection/`; environment execution, PPO, events, metrics, controlled faults.
- **Person 3 — Verification and diagnosis:** `backend/verification/`, `backend/diagnosis/`; requirement models, deterministic checks, incident creation, evidence packaging, Meta AI investigation.
- **Person 4 — Provenance, recovery, evaluation, persistence:** `backend/provenance/`, `backend/recovery/`, `backend/evaluation/`, `backend/database/`; lineage, migrations, artifact impact, validated recovery, evaluation.
- **Shared:** `shared/`, root dependency files, API composition, CI, Docker Compose, common config, and end-to-end tests. Any shared-file change must be announced and reviewed by affected owners.

Person 4 owns database infrastructure and migrations, but does not own every module's persistence behavior. Each module owns its repository/service logic and uses the agreed session and model contracts.

## 6. Proposed directory layout

Treat this as the target, not permission to blindly create all folders. Follow existing repository conventions when they already exist.

```text
self-healing-rl-studio/
├── AGENTS.md
├── frontend/
│   ├── AGENTS.md
│   └── app/
├── backend/
│   ├── AGENTS.md
│   ├── api/
│   ├── environments/
│   ├── training/
│   ├── monitoring/
│   ├── fault_injection/
│   ├── verification/
│   ├── diagnosis/
│   ├── provenance/
│   ├── recovery/
│   ├── evaluation/
│   └── database/
├── shared/
│   ├── schemas/
│   ├── events/
│   └── contracts/
├── tests/
│   ├── integration/
│   └── end_to_end/
├── docs/
├── docker/
├── docker-compose.yml
├── pyproject.toml
├── package.json
└── README.md
```

## 7. Cross-module data contracts

All inter-module contracts must live in one agreed location, preferably `shared/schemas/` or the existing equivalent. Do not duplicate Pydantic models, TypeScript interfaces, enums, or event definitions in separate modules. If TypeScript types are generated from a canonical schema, use the generated types rather than hand-maintaining a second version.

### 7.1 Common identifiers

Use stable identifiers for:
- `project_id`
- `experiment_id`
- `run_id`
- `environment_id`
- `environment_version`
- `agent_config_id` or immutable agent configuration fingerprint
- `event_id`
- `episode_id`
- `rollout_id`
- `training_update_id`
- `checkpoint_id`
- `requirement_id`
- `incident_id`
- `recovery_id`
- `evaluation_id`

Identifiers must be unambiguous within their declared scope. Do not use display names as primary identifiers. Never silently reuse an ID for a different artifact.

### 7.2 Event contract

An event should include, where applicable:
- schema version
- event ID
- event type
- project, experiment, and run IDs
- environment ID and immutable environment version
- episode/timestep/update identifiers
- event timestamp in UTC
- monotonic sequence or ordering information
- payload validated against its event type
- correlation/causation IDs where useful
- source component and software version

Do not fabricate expected values when none are known. `expected_reward` should be absent/null when no applicable confirmed contract exists, not guessed. Keep expected values and actual observations distinct.

Example only:

```json
{
  "schema_version": "1.0",
  "event_id": "evt_example",
  "event_type": "reward_observed",
  "run_id": "run_example",
  "environment_version": "warehouse_v1",
  "episode_id": "episode_10",
  "timestep": 1200,
  "actual_reward": 25.0,
  "requirement_id": "req_goal_reward",
  "timestamp": "2026-10-25T12:00:00Z"
}
```

### 7.3 Requirement contract

A requirement records:
- unique ID and version
- human-readable description
- machine-checkable rule/type and parameters, when supported
- source: `developer_confirmed`, `test_derived`, `code_inferred`, or equivalent enum
- confirmation status
- tolerance and comparison semantics
- applicable environment version/scope
- author/created time and change history

A hard violation must identify which active rule was violated and include evidence. Inferred requirements are hypotheses until confirmed or supported by an explicit policy.

### 7.4 Incident contract

An incident records:
- incident/run/requirement IDs
- violation type and severity
- status and timestamps
- evidence event IDs and evidence references
- detection method and detector version
- whether the violation is confirmed, suspected, or unresolved
- diagnosis status, separate from detection status
- links to relevant environment version and artifacts

Do not conflate “incident detected,” “root cause likely,” and “cause proven.”

### 7.5 Recovery and evaluation contracts

A recovery record includes:
- incident ID
- proposed and executed actions separately
- source and target checkpoint IDs
- environment/configuration fingerprints
- compatibility-check results
- approval/authorization state where needed
- execution status, timestamps, logs, and failure reason
- validation and evaluation status

An evaluation record includes:
- evaluation ID and recovery/run IDs
- evaluation environment version
- evaluation policy/checkpoint fingerprint
- episode count and seeds
- metric definitions and results
- baseline identities
- uncertainty or confidence intervals when computed
- completed/failed/inconclusive status

All numerical example values in docs and UI fixtures must be labeled as examples or mock data.

## 8. API and execution architecture

- Frontend talks to the backend through documented HTTP APIs and an explicitly defined live-update channel.
- Frontend must not access the database directly.
- Training must not run synchronously inside a long-lived HTTP request. API handlers validate and schedule work; a controlled worker executes it.
- Use a small in-process worker for the MVP if it is sufficient and reliable; introduce Redis/Celery only when justified.
- API handlers must validate requests, enforce state transitions, return stable error shapes, and avoid leaking secrets or filesystem paths.
- Keep business logic out of route handlers. Route handlers orchestrate service-layer calls.
- Use idempotency keys or equivalent protection for operations that might be retried, especially start/stop/recovery actions.
- Define the source of truth for run status and transitions.
- WebSocket or server-sent-event messages must use versioned schemas and reconnect/resync behavior. A client reconnect should be able to fetch a current snapshot and then resume updates.
- Do not use in-memory events as the only durable record of incidents or recovery actions.

## 9. Run lifecycle and state transitions

Define and enforce an explicit lifecycle. Suggested states:
`created -> queued -> starting -> running -> stop_requested -> stopped`
and terminal alternatives `completed`, `failed`, `cancelled`.

Recovery and evaluation have their own state machines. Do not overload a training run's status to represent a recovery or evaluation status.

Rules:
- Reject illegal transitions with a typed error.
- Repeated stop requests should be safe/idempotent.
- A failed run must record a sanitized failure reason and diagnostic reference.
- Terminal states should not silently transition back to running.
- Restarting training creates a new run or a clearly versioned continuation record; never rewrite history.
- Keep the UI status derived from backend state, not local guesses.

## 10. Reproducibility and artifact integrity

Record:
- Python and key library versions.
- Environment ID/version and configuration fingerprint.
- Agent algorithm and complete configuration.
- Seed(s), timestep counters, episode/update counters.
- Training code revision when available.
- Checkpoint hash and metadata.
- Observation/reward normalization state, where used.
- Optimizer and RNG state when needed for faithful continuation.
- Event/rollout/update/checkpoint associations.
- Fault injection schedule and exact parameters.

Checkpoint writes should be atomic where feasible: write to a temporary location, flush/close, validate, then rename. Never overwrite the only known-good checkpoint. Verify checkpoint metadata and integrity before restoration.

## 11. Security and safe operation

- Never commit API keys, credentials, private datasets, tokens, or local `.env` files.
- Provide `.env.example` with placeholder values only.
- Validate paths and prevent path traversal.
- Do not execute arbitrary model-generated code, shell commands, serialized pickle files from untrusted sources, or arbitrary user code with broad privileges.
- Treat model responses, logs, environment descriptions, and developer-supplied code as untrusted input.
- Restrict Meta AI prompts to relevant evidence; do not include secrets or unrelated personal data.
- Apply request size limits, timeouts, rate limits on sensitive endpoints, and authentication/authorization appropriate to the deployment.
- Recovery actions must be allow-listed, validated, logged, and reversible where possible.
- Do not silently modify source code. Any automated code patching, if added in the future, requires a separate review/approval design.
- Use Docker or another isolation mechanism for any future untrusted code execution; no privileged containers, host mounts, or unrestricted network by default.
- Avoid logging full secrets, full authorization headers, or unbounded raw user content.

## 12. AI diagnosis requirements

- The AI investigator is advisory; deterministic verification and recovery validators remain authoritative for supported contracts.
- Provide evidence with stable IDs, source, timestamp, and relevant context.
- Ask for structured output validated against a schema.
- Handle provider timeouts, rate limits, invalid JSON, refusals, and unavailable credentials.
- Set bounded retries with exponential backoff and jitter; do not retry indefinitely.
- Record model/provider identifiers and prompt/schema versions where allowed.
- Do not report a confidence score unless the model/API or a defined scoring method actually supplies one. If a model-generated confidence is shown, label it as an estimate, not a calibrated probability.
- Distinguish observed facts, hypotheses, and recommendations.
- Do not let AI directly execute actions or choose an arbitrary checkpoint without deterministic compatibility validation.

## 13. Recovery correctness

- Unknown lineage means “impact unknown,” not “unaffected.”
- Exposure to a faulty environment does not alone prove that an update is damaged.
- A recovery plan must identify why the chosen checkpoint is compatible with the target environment and training configuration.
- For PPO, discard pending on-policy experience that is incompatible with the corrected environment or policy state; collect fresh experience after correction as appropriate.
- Restore all relevant state for the supported recovery path, not only model weights when optimizer, normalization, counters, or RNG state are required.
- Validate checkpoint existence, hash, environment compatibility, algorithm compatibility, and required metadata before executing a restore.
- Record both the plan and actual outcome.
- If validation fails, do not proceed; return an explicit blocked/failed result with a reason.
- Recovery is not “successful” until a defined evaluation completes and meets the configured acceptance criteria. If results are mixed or statistically weak, report inconclusive rather than success.

## 14. Evaluation methodology

- Compare the original/faulty/recovered policy in the same healthy evaluation environment and comparable conditions.
- Separate training metrics from evaluation metrics.
- Use a documented episode count and fixed evaluation seeds for paired comparisons where practical.
- Use multiple seeds where feasible; report mean and variability rather than a single lucky episode.
- Define metrics and denominators clearly.
- Track success rate, reward, episode length, collision rate, and recovery duration as appropriate to the environment.
- Measure detection precision/recall and false-intervention rate when enough labeled test cases exist.
- Never hard-code results to create a compelling demo.
- Keep test fixtures clearly labeled and never mix fixture metrics with live experiment metrics.

## 15. Code quality and style

### Python
- Use type hints for public functions and important data structures.
- Prefer small, cohesive functions and explicit dependency injection.
- Use Pydantic models for external/config boundaries.
- Use structured logging rather than print statements in application code.
- Avoid broad `except Exception` unless it is at a process boundary, logs safe context, and preserves the error state.
- Do not hide errors with default values that make a run appear successful.
- Use context managers for files, database sessions, and external clients.
- Keep import side effects minimal; do not start training or network calls on import.

### TypeScript/React
- Use strict TypeScript; avoid `any` except at a narrow, documented boundary.
- Keep UI components focused; separate data fetching, state transitions, and visual components.
- Model loading/empty/error/success states explicitly.
- Do not fake live state or silently substitute demo values in production paths.
- Ensure accessible labels, keyboard interaction, and responsive layout.
- Cancel/ignore stale requests where appropriate.
- Avoid leaking backend internals or raw exception details to users.

### General
- Use clear names and consistent formatting.
- Avoid duplicated business logic and magic numbers.
- Add comments to explain non-obvious decisions, not to narrate every line.
- Keep functions and modules appropriately scoped.
- Prefer explicit enums/constants to stringly typed status values.
- Document assumptions and limitations.

## 16. Error handling and observability

Every module must:
- Use stable, typed error categories at module/API boundaries.
- Log enough context to diagnose failures without exposing secrets.
- Propagate failure states instead of converting them to success-shaped responses.
- Define timeout behavior for external services and long-running operations.
- Distinguish user validation errors, conflicts, unavailable dependencies, internal errors, and timeouts.
- Add correlation IDs so logs can be followed across a run, incident, recovery, and evaluation.
- Ensure logs and event storage are bounded/rotated in local development.

For the UI, show actionable, non-sensitive error messages and a retry path only when retry is safe.

## 17. Testing policy

Add tests with each feature. Do not postpone all tests until integration.

Required test categories:
- Unit tests for pure functions, rule evaluation, state transitions, and metrics.
- Contract tests for shared schemas and API response shapes.
- Integration tests for event flow and persistence.
- Fault-injection tests for each supported fault.
- Negative tests for malformed payloads, missing evidence, unavailable Meta AI credentials, incompatible checkpoints, and invalid recovery transitions.
- End-to-end test for the canonical warehouse reward-scaling scenario.
- Security tests for path validation, request bounds, and disallowed operations where applicable.

Tests must be deterministic and not require external credentials unless explicitly marked as optional integration tests. Never make ordinary CI depend on a live Meta AI call.

## 18. Dependency and environment management

- Inspect existing tooling before adding a new dependency manager.
- Pin or constrain dependencies consistently with the repository's established lockfile approach.
- Keep frontend and backend dependencies separate where practical.
- Use environment variables for runtime secrets and configuration.
- Document Windows and Linux setup commands if both are supported.
- Do not introduce a new service, database, broker, or framework without explaining why it is needed.
- Avoid unnecessary heavyweight dependencies.
- Do not change global Python, Node, or system configuration as part of routine project code.

## 19. Git and collaboration rules

- Work on a feature branch; do not commit directly to the shared integration/main branch unless the team explicitly agrees.
- Keep commits focused and descriptive.
- Before editing, inspect `git status`, current branch, and the relevant files.
- Do not overwrite another person's uncommitted changes.
- Do not use destructive commands (`git reset --hard`, forced checkout, bulk deletion, destructive migration) without explicit coordination and a verified backup.
- Do not commit generated artifacts, model checkpoints, local datasets, credentials, or huge logs unless explicitly required.
- Shared schemas, dependency manifests, root configs, migrations, and API routers require coordination and review from affected owners.
- Do not silently reformat or rename large unrelated parts of the repository.
- In a PR, describe behavior, contract changes, test commands/results, migration effects, risks, and known limitations.

## 20. Definition of done

A task is not complete merely because code was written. It is complete when:
1. It satisfies the acceptance criteria.
2. It uses the agreed contracts.
3. It has tests for expected and failure behavior.
4. Relevant tests and static checks pass, or failures are clearly reported.
5. Errors and state transitions are handled explicitly.
6. Security and provenance requirements are preserved.
7. Documentation/config examples are updated where needed.
8. No secrets, fake metrics, unrelated changes, or unexplained generated files are included.
9. The owning person has reviewed cross-module changes.
10. Limitations and unverified behavior are disclosed.

## 21. Canonical demo acceptance criteria

The initial end-to-end demonstration must show:
- A project and warehouse experiment can be configured.
- A seeded PPO run produces real execution events and checkpoints.
- A controlled reward-scaling fault changes a goal reward from the configured expected value to a different observed value.
- The verifier detects a violation because a confirmed contract was violated, not merely because reward is low.
- The incident references real event IDs and environment version.
- Meta AI receives real, relevant evidence and returns a structured hypothesis, or the UI clearly reports that the provider is unavailable.
- Provenance identifies artifacts as exposed/potentially affected/unknown based on records.
- A supported recovery action is validated before execution.
- The recovered policy is evaluated under a healthy environment against defined baselines.
- The result is based on actual metrics and reports uncertainty/limitations.
- The audit trail shows each step and its outcome.

## 22. Agent workflow when asked to change code

Before coding:
1. Read root and relevant module `AGENTS.md` files.
2. Inspect current code, tests, configuration, and git status.
3. Identify the owning module and downstream consumers.
4. State the plan and affected contracts for non-trivial changes.
5. Reuse existing abstractions rather than creating duplicate implementations.

While coding:
1. Make the smallest complete change.
2. Validate input at boundaries.
3. Add tests for success and failure.
4. Keep contracts and docs in sync.
5. Avoid changing other modules without coordination.

Before finishing:
1. Run the most relevant tests and lint/type checks available.
2. Inspect the diff for accidental changes and secrets.
3. Report exactly what changed and what was tested.
4. Distinguish verified results from assumptions or untested behavior.
5. Mention required environment variables/services and follow-up work.

## 23. Explicit non-goals

Unless the team formally changes scope, do not:
- Promise to repair every possible RL environment bug.
- Treat LLM output as ground truth.
- Infer developer intent silently and enforce it as a confirmed requirement.
- Prove causal model damage from simple temporal overlap.
- Automatically patch arbitrary user code.
- Execute untrusted code or shell commands with unrestricted permissions.
- Use fabricated charts, invented checkpoint history, or hard-coded recovery outcomes in the real demo.
- Add large-scale distributed infrastructure before the MVP requires it.

## 19. Git Workflow, Commits, and Pull Requests (MANDATORY)

These rules apply to every team member, coding agent, and automation working in this repository. They are mandatory and must not be overridden by individual module instructions.

### 19.1 Development Branch

- **Always work on the `backend3` branch.**
- Before modifying files, creating commits, or pushing changes, run `git branch --show-current` and verify that the active branch is `backend3`.
- Never perform development work directly on `main`.
- Never create or switch to a feature, bug-fix, temporary, or alternative branch unless the repository owner explicitly authorizes an exception.
- If `backend3` does not exist locally, check the remote repository and safely check out the existing remote branch. Do not create a replacement without verifying the repository state.
- Inspect `git status --short` before switching branches. Preserve all uncommitted changes and other contributors' work.
- If the working tree contains changes that make switching unsafe, stop and resolve the situation without discarding work.
- All feature development, bug fixes, refactoring, tests, and documentation changes must be performed on `backend3`.

### 19.2 Strict Protection of `main`

**NEVER commit to, push to, or make direct changes on `main` unless the repository owner explicitly authorizes that specific action.**

- Do not create commits while checked out on `main`.
- Do not push `HEAD` or any local branch directly to the remote `main` branch.
- Do not use commands that explicitly push changes to `main`.
- Do not switch to `main` to implement, test, or commit a change.
- Do not bypass branch protection, rewrite `main` history, or force-push to `main`.
- Do not interpret a request to implement a feature, fix a bug, commit changes, push code, or create a PR as permission to commit or push directly to `main`.
- The only permitted default workflow for delivering changes is to commit on `backend3`, push `backend3` when required, and open a pull request targeting `main`.
- A request to create or update a pull request does not authorize merging it.
- Only an explicit instruction from the repository owner can authorize an exception to these restrictions. The authorization must clearly identify the action permitted.
- Even when an exception is authorized, prefer the least risky operation and never rewrite shared history without explicit authorization.

### 19.3 Frequent, Meaningful Commits

Make frequent commits at meaningful development milestones. Do not accumulate an entire feature, multiple unrelated fixes, and documentation changes into one unnecessarily large commit.

- Each commit must represent a coherent, reviewable unit of work.
- Commit after completing a meaningful feature component, bug fix, test group, refactor, or documentation update.
- Do not commit unfinished, broken, or unrelated changes merely to increase commit frequency.
- Keep each commit focused on one logical purpose.
- Before creating a commit, inspect the working tree and stage only the files belonging to that change.
- Never include unrelated changes or another contributor's work without understanding and obtaining the appropriate approval.
- Do not commit secrets, credentials, local `.env` files, private datasets, model checkpoints, large logs, or generated artifacts unless explicitly required and approved.
- Review staged changes using `git diff --cached` before committing.
- Run relevant tests and checks before committing whenever practical.
- Never claim that a commit was created unless the command succeeded.

### 19.4 Commit Messages Must Be One Line

**Every commit message must be a single, concise, meaningful line.**

- Use the format: `<type>: <description>`.
- Use imperative, specific wording that describes the change.
- Do not use multi-line commit messages.
- Do not include a long body, paragraphs, checklists, or unrelated details in a commit message.
- Avoid vague messages such as `updates`, `changes`, `fix`, `final`, `working`, or `misc`.
- Do not combine unrelated changes merely to fit them into one message.
- Keep the message concise and easy to understand in `git log --oneline`.

Examples of valid commit messages:

- `feat: add intent requirement validation`
- `feat: detect reward contract violations`
- `fix: reject malformed execution events`
- `fix: preserve incident evidence on diagnosis failure`
- `test: cover verification edge cases`
- `refactor: separate diagnosis from incident detection`
- `docs: document recovery validation contracts`
- `chore: configure backend linting`

Example:

`git commit -m "feat: add intent requirement validation"`

The `-m` argument must contain one line only. Do not use multiple `-m` arguments to construct a multi-paragraph commit message.

### 19.5 Push Rules

- Push development changes to the remote `backend3` branch only.
- Before pushing, verify the active branch and inspect the intended commits.
- Use the appropriate remote name after verifying it; do not assume the remote is always named `origin`.
- Never push directly to `main` without explicit authorization from the repository owner.
- Do not force-push or rewrite shared branch history without explicit authorization.
- If a push is rejected, inspect the reason and remote history before taking further action.
- Never use destructive operations to force a push through.
- Report whether the push actually succeeded.

### 19.6 Pull Request Rules

**Whenever the repository owner requests a pull request, create or update a PR from `backend3` into `main`.**

The required direction is:

- **Source/head branch:** `backend3`
- **Target/base branch:** `main`

The required workflow is:

`Develop on backend3` → `Make meaningful one-line commits` → `Push backend3` → `Open PR from backend3 to main`

Mandatory rules:

- Never create a PR from `main` to `backend3`.
- Never substitute another source branch unless the repository owner explicitly authorizes an exception.
- Before opening the PR, fetch remote references when possible and inspect the changes that will be included.
- Review the diff against `main` for unintended modifications, accidental deletions, secrets, and unrelated changes.
- Run relevant tests and checks and accurately report their results.
- Include a useful PR title and description explaining the changes, tests performed, known limitations, and relevant risks.
- If a PR from `backend3` to `main` already exists, inspect and update the existing PR instead of creating a duplicate.
- Do not merge the PR unless the repository owner explicitly requests and authorizes the merge.
- Do not claim a PR was opened unless its creation is confirmed.
- If authentication, permissions, branch protection, conflicts, or tooling prevent PR creation, report the actual blocker.

### 19.7 Mandatory Git Checklist

Before making changes:
1. Run `git branch --show-current`.
2. Confirm that the branch is `backend3`.
3. Inspect `git status --short`.
4. Review existing changes and relevant files.

Before each commit:
1. Confirm the branch is `backend3`.
2. Inspect the changes.
3. Stage only relevant files.
4. Review `git diff --cached`.
5. Run relevant tests when practical.
6. Create a meaningful, single-line commit message.

Before each push:
1. Confirm the branch is `backend3`.
2. Inspect the commits being pushed.
3. Push to `backend3`, never directly to `main`.
4. Confirm the push result.

Before each PR:
1. Confirm the source is `backend3`.
2. Confirm the target is `main`.
3. Review the complete PR diff.
4. Run relevant checks.
5. Create or update the PR.
6. Verify the PR URL and report its status.

### 19.8 Final Rule

**Work only on `backend3`. Make frequent, meaningful commits with one-line commit messages. Push development changes only to `backend3`. When asked to create a PR, create it from `backend3` to `main`. Never commit to or push directly to `main` unless the repository owner explicitly authorizes that specific action. Never merge a PR without explicit authorization.**