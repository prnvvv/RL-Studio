# Project Tasks & Roadmap

## [ ] Scaffold Person 2 RL execution substrate (env, PPO, monitoring, faults)
- **Status:** Pending
- **Created:** 2026-10-25 18:09
- **Category:** Feature

### Context / Goal
Audit on 2026-10-25 found the repository contains only a tracked `.gitignore`; `backend/environments/`, `backend/training/`, `backend/monitoring/`, `backend/fault_injection/` and `shared/schemas/` do not exist. Build the MVP RL substrate: one Gymnasium 2D warehouse-navigation environment, SB3 PPO training, canonical execution events, metrics aggregation, and three allow-listed faults (reward scaling, observation corruption, invalid termination).

### Action Items
- [ ] Agree canonical event fields with Person 3 and checkpoint metadata with Person 4 (blocks contract-dependent work)
- [ ] Establish toolchain floor: `pyproject.toml` with pinned `gymnasium` + `stable-baselines3`, project-local virtualenv, lint/format convention, test markers for slow RL tests
- [ ] Implement `backend/environments/` warehouse env: observation/action spaces, reset/step signatures, coordinate convention, terminated/truncated semantics, seeded init, info payload
- [ ] Add config validation (grid bounds, obstacles, start/goal, rewards, reachability) returning useful errors instead of silent repair
- [ ] Add canonical config serialization + stable fingerprint with documented normalization rules
- [ ] Implement `backend/training/` PPO wrapper, validated hyperparameters, seed discipline (python/numpy/env/model/eval), run lifecycle states with idempotent start/stop
- [ ] Add callbacks for metrics + checkpointing with bounded memory and visible callback failure
- [ ] Implement atomic checkpoint writes with integrity hash and metadata (run/env/algorithm fingerprints, counters, versions)
- [ ] Implement `backend/monitoring/` raw episode metrics vs rolling aggregates, each with explicit window/denominator/units and empty-episode behavior
- [ ] Implement `backend/fault_injection/` reward scaling, observation corruption, termination fault with exact trigger boundary (before/after step) and no cross-run leakage
- [ ] Emit schema-validated events with unique IDs, UTC timestamps, sequence ordering; make publication failure visible
- [ ] Tests: env API conformance, seeded determinism, boundaries/obstacles, invalid configs, fault timing, checkpoint round-trip, lifecycle idempotency, callback failure, metric aggregation
- [ ] PPO smoke test on small timestep budget (CartPole optional, must not delay warehouse path)

### Technical Details / Notes
- Python 3.13.3 via pyenv is the only interpreter configured; no repo-local `.venv` or lockfile exists. `torch 2.7.1`, `numpy 2.2.6`, `pytest 8.4.1`, `pydantic 2.11.5` are installed globally; `gymnasium`, `stable-baselines3`, and `ruff` are missing.
- Cross-module contracts must live in `shared/schemas/`; do not duplicate models across modules (root AGENTS.md §7).
- Do not implement PPO from scratch; do not claim pause/resume without tests.
- Record known nondeterminism (hardware/library variance) rather than promising bitwise reproducibility.

---

## [ ] Fix: root AGENTS.md is git-ignored and untracked
- **Status:** Pending (needs team review — root/shared file)
- **Created:** 2026-10-25 18:09
- **Category:** Fix

### Context / Goal
`git check-ignore -v AGENTS.md` reports `.gitignore:1:AGENTS.md`. The repository-wide engineering contract exists only on this machine and will not reach any other clone of `main`/`dev3`. Any future module-level `AGENTS.md` (e.g. `backend/AGENTS.md`) is also silently ignored.

### Action Items
- [ ] Decide with the team: commit `AGENTS.md` (remove the ignore rule) or keep it intentionally local
- [ ] If keeping it local, decide how module-level `AGENTS.md` files are shared (force-add or rename)
- [ ] Verify `.gitignore` still ignores `AGENTS.md`-named local scratch files if the rule is removed

### Technical Details / Notes
- Commit `5f5cc05 "create: backend folder and AGENTS.md"` actually only added the `.gitignore` line; no `AGENTS.md` or `backend/` was committed.
- Root AGENTS.md §19 requires coordination before changing shared/root config, so this cannot be self-approved.
- `TODO.md` was added to `.gitignore` so task logs stay local.

---

## [x] Scaffold Person 2 RL execution substrate (env, PPO, monitoring, faults) - IN PROGRESS
- **Status:** In Progress
- **Updated:** 2026-10-27
- **PR:** #14 (backend2 -> main)

### Completed
- [x] Shared schemas in `shared/schemas/` (contracts/events/requirements) with cross-module contracts
- [x] `backend/environments/` warehouse env, config validation (reachability/bounds), fingerprints
- [x] `backend/training/` PPO wrapper with seed discipline, run lifecycle states, callbacks (metrics/checkpointing)
- [x] `backend/monitoring/` episode/rolling metrics, schema-validated event emission
- [x] `backend/fault_injection/` reward scaling, observation corruption, invalid termination with exact trigger boundary
- [x] Atomic checkpoint writes with integrity hash/metadata
- [x] Frontend schema types mirrored in `frontend/src/schemas/shared.ts`
- [x] CI unified with schema validation for FE/BE on all pushes to main + PRs

### Remaining
- [ ] PPO smoke test on small timestep budget (CartPole optional)
- [ ] More comprehensive tests (fault timing, checkpoint round-trip, lifecycle idempotency)
- [ ] Integration with API layer if needed

### Additional Tests Added
- [x] `backend/tests/test_env_smoke.py` - env reset/step API conformance
- [x] `backend/tests/test_faults.py` - fault timing boundaries and leakage
- [x] `backend/tests/test_checkpoints.py` - atomic checkpoint round-trip with metadata/hash
- [x] `backend/tests/test_lifecycle.py` - lifecycle idempotency

- [x] PPO smoke test on small timestep budget

- [x] Metric aggregation and event ordering tests

### Status Update
- [x] All Person 2 substrate components implemented (env/training/monitoring/faults)
- [x] Tests passing (9/9) including PPO smoke, faults, checkpoints, lifecycle, metrics, events
- [x] CI passing with schema validation
