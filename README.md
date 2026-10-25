<div align="center">

<!-- Banner -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=0:667EEA,100:764BA2&height=300&section=header&text=Self-Healing%20RL%20Studio&fontSize=70&animation=fadeIn&fontAlignY=38&desc=Find%2C%20trace%2C%20and%20safely%20recover%20from%20faults%20in%20RL%20training&descAlignY=55&descAlign=50" width="100%" />

<!-- Badges -->
[![Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)]()
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)]()
[![Algorithm](https://img.shields.io/badge/algorithm-PPO%20%C2%B7%20Stable--Baselines3-blueviolet.svg)]()
[![License](https://img.shields.io/badge/license-TBD-lightgrey.svg)]()

</div>

> **Project status: pre-alpha — design phase.**
> This repository currently contains only an engineering contract and local planning notes. There is no application code, no dependency manifest, no tests, and no runnable demo yet. Everything marked *planned* below describes intended target behavior, not shipped functionality.

## Overview

Self-Healing RL Studio is a developer platform for finding, investigating, tracing, and safely recovering from faults in reinforcement-learning environments and training runs. Its goal is to make RL failure modes **observable and auditable** rather than anecdotal: capture what the developer intended, record what actually executed, detect concrete contract violations, and only then attempt a validated recovery.

The first demonstrator is deliberately narrow: a reproducible 2D warehouse-navigation environment trained with PPO, plus one canonical incident — a configured goal reward of `100` observed as `25` because of an injected reward-scaling fault. A test should prove the fault happened, a verifier should flag a confirmed contract violation, and a recovered policy should be evaluated against a healthy baseline.

The project is built on a few non-negotiable principles:

- **Evidence before explanation.** Raw observations and provenance are recorded before any model interprets them.
- **Confirmed intent before hard claims.** Developer-confirmed contracts are separated from inferred hypotheses.
- **Deterministic checks for hard invariants.** AI is used to prioritize hypotheses, never as the sole enforcer of a safety-critical rule.
- **Fail closed on destructive operations.** Unknown lineage or unverified checkpoints block automatic recovery.
- **Truthful reporting.** Mock data, incomplete lineage, uncertain diagnoses, and unverified recoveries are labeled as such.

## Key Features

All items are *planned*; none are implemented at the current commit.

- **Gymnasium warehouse environment** — configurable grid, obstacles, start/goal cells, step budget, reward and collision settings, seeded determinism, and a canonical configuration fingerprint bound to every run.
- **PPO training engine** — Stable-Baselines3 PPO with validated hyperparameters, explicit run lifecycle states, idempotent start/stop, and atomic checkpoint writes with integrity hashes.
- **Canonical execution events** — schema-validated run, episode, step, collision, checkpoint, and metric events with stable IDs, UTC timestamps, and ordering metadata.
- **Raw metrics vs. rolling aggregates** — episode reward, mean reward, episode length, success rate, and collision rate, each with an explicit window, denominator, and missing-data rule.
- **Controlled fault injection** — allow-listed reward scaling, observation corruption, and invalid-termination faults with exact trigger boundaries and no cross-run leakage.
- **Deterministic verification** — developer-confirmed requirements evaluated against real evidence, producing incidents that reference actual event IDs and environment versions.
- **Advisory AI diagnosis** — a replaceable provider interface over real evidence, with structured output and explicit "provider unavailable" handling.
- **Provenance and recovery** — artifact exposure tracking, compatibility-checked checkpoint restore, fresh on-policy experience collection, and post-recovery evaluation against baselines.

## Tech Stack & Prerequisites

**Verified in the current checkout**

| Requirement | Status |
|---|---|
| Python 3.13.3 | Installed (via pyenv) |
| `numpy` 2.2.6, `torch` 2.7.1, `pydantic` 2.11.5 | Installed globally |
| `pytest` 8.4.1, `mypy` 1.19.1, `black` | Installed globally |
| `fastapi` 0.117.1, `SQLAlchemy` 2.0.43, `uvicorn` 0.37.0 | Installed globally |
| `gymnasium`, `stable-baselines3`, `ruff` | **Not installed** |
| Project virtualenv, `pyproject.toml`, lockfile | **Not present** |

**Planned stack**

- **Backend:** Python 3.13, FastAPI, SQLAlchemy, Pydantic for boundary validation
- **RL:** Gymnasium, Stable-Baselines3 (PPO), PyTorch
- **Frontend (Person 1):** TypeScript / React dashboard over the documented HTTP API and a live-update channel
- **Storage:** relational database owned by the provenance/persistence layer

> The effect of a fault is evaluated in the same healthy environment. Training metrics and evaluation metrics must never be merged into a single series.

## Getting Started

### Current state

Cloning the repository gives you a `.gitignore` and nothing else that is tracked. There is nothing to install and no app to run yet — the engineering contract (`AGENTS.md`) and the local task log (`TODO.md`) are currently **git-ignored**, so a fresh clone does not include them.

```bash
git clone https://github.com/prnvvv/RL-Studio.git
cd RL-Studio
git status
```

### Planned setup (not yet runnable)

These commands become valid once the toolchain scaffold from `TODO.md` lands:

```bash
# 1. Clone and enter the repository
git clone https://github.com/prnvvv/RL-Studio.git
cd RL-Studio

# 2. Create an isolated environment (do not install RL deps globally)
python3.13 -m venv .venv
source .venv/bin/activate

# 3. Install the project with dev extras
#    pyproject.toml does not exist yet, so this will fail today
python -m pip install -e ".[dev]"

# 4. Configure environment variables
cp .env.example .env   # .env.example is planned; never commit real secrets
```

Planned environment variables (illustrative — no `.env.example` exists yet):

```dotenv
# Optional AI diagnosis provider; the platform must degrade cleanly when unset
META_AI_API_KEY=
META_AI_MODEL=
# Local database and API configuration
DATABASE_URL=
API_HOST=127.0.0.1
API_PORT=8000
```

### Running it (planned)

```bash
# Start the backend API (planned entry point)
uvicorn backend.api.main:app --reload

# Start the frontend dashboard (planned)
cd frontend && npm install && npm run dev

# Run the fast test suite
pytest -m "not slow"
```

None of these commands work at the current commit.

## Usage Guide & Examples

There is no API or CLI to call yet. The intended canonical demo workflow, which the acceptance criteria are written against, is:

1. **Create a project and warehouse experiment** with an explicit environment configuration and seed.
2. **Start a seeded PPO run.** The run records real execution events and periodic checkpoints.
3. **Inject a reward-scaling fault** that multiplies the configured goal reward by `0.25`, so the expected `100` is observed as `25`.
4. **Detect the violation deterministically** because the confirmed goal-reward contract was violated — not merely because the reward curve looks low.
5. **Open an incident** that references the actual event IDs and the immutable environment version.
6. **Request AI diagnosis** over the frozen evidence package. If no provider is configured, the UI must say so instead of inventing a hypothesis.
7. **Trace artifact exposure** and mark affected checkpoints as exposed, potentially affected, or unknown.
8. **Restore a compatible checkpoint** only after deterministic compatibility and integrity checks pass, then collect fresh experience.
9. **Evaluate the recovered policy** in the healthy environment against defined baselines, and report measured outcomes with uncertainty.

Illustrative event shape — **not output from a real run**:

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

Every path below is the **target** layout; only `.gitignore` is currently tracked.

```text
RL-Studio/
├── AGENTS.md                  # repository-wide engineering contract (currently git-ignored)
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

## Roadmap

| Area | Status |
|---|---|
| Engineering contract (`AGENTS.md`) | Written; not committed (git-ignored) |
| Toolchain (`pyproject.toml`, venv, lint config) | Not started |
| Warehouse environment + validation + fingerprint | Not started |
| PPO training, lifecycle, checkpoints | Not started |
| Monitoring metrics | Not started |
| Fault injection (reward scaling, observation corruption, invalid termination) | Not started |
| Shared event/requirement/incident schemas | Not started |
| Verification, diagnosis, provenance, recovery, evaluation | Owned by other modules; not started |
| Canonical end-to-end demo | Not started |

## Contributing

- Work on a feature branch; do not commit directly to `main` or the shared integration branch.
- Read the repository-wide `AGENTS.md` before changing code. It defines module ownership, contract rules, security constraints, and the definition of done.
- Shared contracts live in `shared/`. Do not duplicate Pydantic models, TypeScript interfaces, or event definitions in individual modules.
- Add tests with each feature — including failure cases — and report the exact commands run and their results.
- Do not commit secrets, model checkpoints, large logs, or fabricated metrics. Numerical examples in docs and fixtures must be labeled as examples.

### Known open issues

- `AGENTS.md` and `TODO.md` are currently matched by `.gitignore`, so collaborators do not receive the engineering contract on clone. This needs a team decision before more code lands.
- There is no `CONTRIBUTING.md` yet; the guidance above is the interim process.

## License

No license has been chosen and no `LICENSE` file is present. Until one is added, treat the contents of this repository as all rights reserved. The badge at the top reads `TBD` for that reason — it is not a claim of MIT licensing.
