# Project Tasks & Roadmap

## [x] Fix: root AGENTS.md is git-ignored and untracked
- **Status:** Done
- **Completed:** 2026-10-27

### Completed
- [x] Removed AGENTS.md from root .gitignore and committed root AGENTS.md
- [x] Verified .gitignore still ignores **/AGENTS.md pattern where appropriate

## [x] Scaffold Person 2 RL execution substrate (env, PPO, monitoring, faults)
- **Status:** Done
- **Completed:** 2026-10-27
- **PR:** #14

### Completed
- [x] Shared schemas in `shared/schemas/` (contracts/events/requirements)
- [x] `backend/environments/` warehouse env, config validation, fingerprints
- [x] `backend/training/` PPO wrapper, lifecycle, callbacks
- [x] `backend/monitoring/` metrics and schema-validated events
- [x] `backend/fault_injection/` reward scaling, observation corruption, invalid termination
- [x] Atomic checkpoint writes with integrity hash/metadata
- [x] Tests: env conformance, determinism, boundaries, faults, checkpoints, lifecycle, metrics, events, PPO smoke (9 tests passing)
