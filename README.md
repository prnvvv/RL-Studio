<div align="center">

<!-- Banner -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=0:667EEA,100:764BA2&height=300&section=header&text=Self-Healing%20RL%20Studio&fontSize=70&animation=fadeIn&fontAlignY=38&desc=Find%2C%20trace%2C%20and%20safely%20recover%20from%20faults%20in%20RL%20training&descAlignY=55&descAlign=50" width="100%" />

<!-- Badges -->
[![Status](https://img.shields.io/badge/status-active-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)]()
[![Algorithm](https://img.shields.io/badge/algorithm-PPO%20%C2%B7%20Stable--Baselines3-blueviolet.svg)]()
[![License](https://img.shields.io/badge/license-proprietary-lightgrey.svg)]()

</div>

> **Project status: active — MVP implemented.** Core backend modules (environments, training, verification, recovery), shared schemas, events, and tests are implemented. Frontend and full end-to-end demo still in progress.

## Overview

Self-Healing RL Studio is a developer platform for finding, investigating, and safely recovering from faults in RL environments and training runs. Core principle: capture developer-confirmed requirements as versioned contracts, record actual execution evidence, detect concrete contract violations, and only then attempt a validated recovery.

The initial demonstrator is a 2D warehouse-navigation environment trained with PPO (Stable-Baselines3), with a canonical incident: a reward-scaling fault that changes the expected goal reward from 100 to 25.

## Key Features (Implemented)

- **Gymnasium warehouse environment** — `Warehouse2DEnv` with Pydantic `WarehouseConfig` validation, BFS reachability check, deterministic fingerprints. Config enforces grid bounds, start/goal distinctness, non-obstacle start/goal, reachability, and reward finiteness.
- **PPO training engine** — Stable-Baselines3 PPO wrapper (`PPOTrainer`) with validated hyperparameters, explicit run lifecycle states (`created → queued → starting → running → stop_requested → stopped`), idempotent start/stop, and atomic checkpoint writes with SHA-256 integrity hashes.
- **Canonical execution events** — schema-validated run, episode, step, collision, checkpoint, and metric events with stable IDs, UTC timestamps, and ordering metadata.
- **Raw metrics vs. rolling aggregates** — episode reward, mean reward, episode length, success rate, collision rate, each with explicit window, denominator, and missing-data rule.
- **Controlled fault injection** — allow-listed reward scaling, observation corruption, and invalid-termination faults with exact trigger boundaries; no cross-run leakage.
- **Deterministic verification** — developer-confirmed requirements evaluated against real evidence, producing incidents that reference actual event IDs and immutable environment versions.
- **Advisory AI diagnosis** — replaceable provider interface over real evidence, with structured output and explicit "provider unavailable" handling.
- **Provenance and recovery** — artifact exposure tracking, compatibility-checked checkpoint restore, fresh on-policy experience collection, and post-recovery evaluation against baselines.
- **Fingerprinting** — stable SHA-256 hashes for configs, agents, and runs (AGENTS.md §10); configs exclude per-run transients; agents bundle algorithm + hyperparameters; runs bundle config + agent + seed.

## Tech Stack (Verified in Current Checkout)

| Requirement | Status |
|---|---|
| Python 3.13 | Installed |
| numpy 2.4.6, torch 2.14.1, pydantic 2.14.1 | Installed globally |
| pytest 9.1.1, mypy 2.4.0, ruff 0.17.3 | Installed globally |
| fastapi, SQLAlchemy, uvicorn | Installed globally |
| gymnasium 1.4.0, stable-baselines3 2.9.2 | Installed globally |
| Project virtualenv, pyproject.toml, lockfile | Present |

**Planned stack (future):**
- Frontend (Person 1): TypeScript / React dashboard over documented HTTP API and live-update channel
- Storage: relational database owned by provenance/persistence layer

> Training metrics and evaluation metrics must never be merged into a single series.

## Getting Started

```bash
git clone https://github.com/prnvvv/RL-Studio.git
cd RL-Studio
git status
```

### Prerequisites

Python 3.13+ with the project virtualenv:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Configure environment variables

```bash
cp .env.example .env   # see .env.example for placeholder values
```

### Run the backend

```bash
# from the repository root
uvicorn backend.main:app --reload --port 8000

# or from backend/ - both entrypoints serve the same canonical app
cd backend
uvicorn app.main:app --reload --port 8000
```

Health check: `curl http://127.0.0.1:8000/health`

### Run the test suite

```bash
pytest -m "not slow"
```

### Quick smoke test (run a PPO training session)

```bash
python -m backend.training.training.ppo
```

## Usage Guide & Canonical Demo Workflow

1. **Create a project and warehouse experiment** with explicit environment configuration and seed.
2. **Start a seeded PPO run.** The run records real execution events and periodic checkpoints.
3. **Inject a reward-scaling fault** that multiplies the configured goal reward by `0.25`, so the expected `100` is observed as `25`.
4. **Detect the violation deterministically** because the confirmed goal-reward contract was violated — not merely because the reward curve looks low.
5. **Open an incident** that references the actual event IDs and the immutable environment version.
6. **Request AI diagnosis** over the frozen evidence package. If no provider is configured, the UI must say so instead of inventing a hypothesis.
7. **Trace artifact exposure** and mark affected checkpoints as exposed, potentially affected, or unknown.
8. **Restore a compatible checkpoint** only after deterministic compatibility and integrity checks pass, then collect fresh experience.
9. **Evaluate the recovered policy** in the healthy environment against defined baselines, and report measured outcomes with uncertainty.

### Illustrative event shape — not output from a real run

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

`expected_reward` is intentionally absent when no confirmed contract exists. Expected and actual values are never merged into one field.

## Project Structure

Every path below is the **target** layout; the current checkout has most modules implemented.

```
RL-Studio/
├── AGENTS.md                  # repository-wide engineering contract
├── backend/
│   ├── api/                   # HTTP routes; orchestration only
│   ├── environments/          # Gymnasium warehouse env, validation, fingerprints
│   ├── training/              # PPO wrapper, run lifecycle, callbacks, checkpoints
│   ├── monitoring/            # episode metrics and rolling aggregates
│   ├── fault_injection/       # allow-listed, parameterized faults
│   ├── verification/          # deterministic requirement checks, incidents
│   ├── diagnosis/             # advisory Meta AI provider interface
│   ├── provenance/            # lineage, artifact exposure, checkpoints
│   ├── recovery/              # validated restore and fresh-experience workflow
│   ├── evaluation/            # post-recovery evaluation against baselines
│   └── database/              # schema, migrations, session contracts
├── frontend/                  # dashboard, forms, visualizations, API client
├── shared/                    # canonical schemas, events, contracts
├── tests/                     # integration and end-to-end suites
├── docs/
└── docker-compose.yml         # planned
```

## Roadmap (Updated)

| Area | Status |
|---|---|
| Engineering contract (`AGENTS.md`) | Written; committed |
| Toolchain (`pyproject.toml`, venv, lint config) | Present |
| Warehouse environment + validation + fingerprint | Implemented |
| PPO training, lifecycle, checkpoints | Implemented |
| Monitoring metrics | Implemented |
| Fault injection (reward scaling, observation corruption, invalid termination) | Implemented |
| Shared event/requirement/incident schemas | Implemented |
| Verification, diagnosis, provenance, recovery, evaluation | Core protocols implemented; adapters in progress |
| Canonical end-to-end demo | Partial (workflow scaffolded, UI pending) |
| Frontend dashboard (Person 1) | In progress |

## Contributing

- Work on a feature branch; do not commit directly to `main` or the shared integration branch.
- Read the repository-wide `AGENTS.md` before changing code. It defines module ownership, contract rules, security constraints, and the definition of done.
- Shared contracts live in `shared/`. Do not duplicate Pydantic models, TypeScript interfaces, or event definitions in individual modules.
- Add tests with each feature — including failure cases — and report the exact commands run and their results.
- Do not commit secrets, model checkpoints, large logs, or fabricated metrics. Numerical examples in docs and fixtures must be labeled as examples.

## License

PROPRIETARY. See `LICENSE` file.