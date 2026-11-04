<div align="center">

<!-- Banner -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=0:FF007F,100:00F0FF&height=300&section=header&text=Self-Healing%20RL%20Studio&fontSize=70&animation=fadeIn&fontAlignY=38&desc=Train%2C%20detect%2C%20diagnose%2C%20and%20recover%20reinforcement%20learning%20runs%20automatically&descAlignY=55&descAlign=50" width="100%" />

<!-- Badges -->
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)
[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

## Overview / About The Project

Self-Healing RL Studio is a full-stack reinforcement learning platform for training agents, verifying that behavior matches developer intent, diagnosing faults, and planning validated recovery.

It combines a FastAPI backend with a React / Vite frontend. Training runs in environments such as the warehouse environment, with Gymnasium, Stable-Baselines3, and SB3 Contrib. Verification converts intent into explicit requirements, runs deterministic checks and anomaly detection, and builds traceable evidence packages. Diagnosis investigates incidents with Meta AI and produces structured findings. Provenance, evaluation, and recovery stages track artifacts, assess impact, and recommend or execute controlled recovery.

Exposure is not proof of causal damage, and recovery execution is not recovery success — the system preserves that distinction throughout.

## Key Features

- **RL studio and training:** PPO training, environment catalog and wrappers, custom parameters, live session management, training history, and real-time event streaming over WebSockets.
- **Environments:** Warehouse environment with fingerprints, configuration management, and extensible environment interfaces.
- **Intent and requirements:** Natural-language intent parsing into structured, traceable verification requirements with source attribution.
- **Verification:** Deterministic rule-based checks, workflow planning, execution analysis, and ML/DL anomaly detection with strict `PASS` / `FAIL` / `UNKNOWN` / `BLOCKED` / `ERROR` statuses.
- **Diagnosis:** Incident detection and classification, evidence construction and validation, bounded Meta AI investigation, and validated diagnosis reports.
- **Recovery and evaluation:** Allow-listed recovery planning and execution, artifact impact analysis, and evidence-based evaluation.
- **Provenance:** Auditable artifact provenance, incident sink integration, and persistent, versioned records across verification, diagnosis, and recovery.
- **AI assistant:** Project-scoped assistant, voice transcription, vision, and segmentation via the Meta Model API, and an advisory investigation workflow.
- **Projects and monitoring:** Multi-project workspace, runs monitoring, reports, and diagnosis / recovery dashboards in the frontend.
- **Fault injection:** Controlled fault injection, including a seeded reward-scaling demo fault for end-to-end validation.

## Tech Stack & Prerequisites

**Backend**

- Python 3.10+
- FastAPI, Uvicorn, SQLAlchemy, Alembic
- Gymnasium, Stable-Baselines3, SB3 Contrib, Torch, NumPy
- LangGraph, LangChain Core, LangSmith
- Pydantic, PyYAML, httpx, websockets
- pytest, mypy, Ruff

**Frontend**

- Node.js >= 22
- React 19, React Router 7, TypeScript 5.6
- Vite 8, Three.js / React Three Fiber / drei
- Clerk, i18next
- Vitest, ESLint, Prettier

**Runtime**

- A Meta Model API key for AI features (`MODAL_API_KEY`)
- SQLite by default; `DATABASE_URL` or `SUPABASE_URL` for other databases

## Getting Started / Setup Instructions

1. **Clone the repository:**

   ```bash
   git clone <repo-url>
   cd RL-Studio
   ```

2. **Set up Python environment and install dependencies:**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   # Development tools
   pip install -e ".[dev]"
   ```

3. **Install frontend dependencies:**

   ```bash
   cd frontend && npm ci
   ```

4. **Environment setup:**

   ```bash
   cp .env.example backend/.env
   # Fill in at minimum MODAL_API_KEY in backend/.env
   ```

   Copy `.env.example` to `.env` for project-level configuration. Never put secrets in frontend code or `VITE_*` variables. Runtime AI inference uses the Meta Model API only.

   Database migrations, if needed:

   ```bash
   alembic upgrade head
   ```

5. **Run the app locally:**

   Full stack (backend + frontend together):

   ```bash
   ./scripts/dev.sh
   ```

   Backend only (FastAPI at `http://127.0.0.1:8000`, docs at `/docs`):

   ```bash
   ./scripts/backend.sh
   # or
   python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
   ```

   Frontend only (Vite dev server):

   ```bash
   cd frontend && npm run dev
   ```

## Usage Guide & Examples

**Health check and API discovery:**

```bash
curl http://127.0.0.1:8000/health
# Interactive API documentation
open http://127.0.0.1:8000/docs
```

**Training lifecycle (API):**

- `POST /api/v1/...` training start, monitoring, history, and evaluation endpoints are exposed under the FastAPI routers in `backend/api/routers/` (`training_history`, `evaluation`, `runs`, `studio`).
- The React frontend at `frontend/src/pages/` provides Training, Studio, Monitoring, Projects, Diagnosis Recovery, Reports, Run Detail, and Settings pages.

**Fault-injection demo (controlled reward-scaling fault):**

```bash
python scripts/seed_demo_fault.py
```

This seeds the canonical demonstration scenario used by verification and diagnosis tests: an observed reward scale that differs from the declared value, which must be confirmed by deterministic checks before any root-cause claim is made.

**Verification, diagnosis, and recovery (API):**

- `POST /api/v1/incidents/{incident_id}/investigations` — bounded, evidence-grounded investigation
- `/recovery-recommendations` — recovery planning for an incident
- Verification, incidents, provenance, and recovery routers live in `backend/api/routers/verification.py`, `incidents.py`, `provenance.py`, and `recovery.py`

**Frontend commands:**

```bash
cd frontend
npm run dev          # dev server
npm run build        # production build
npm run typecheck    # TypeScript check
npm run lint         # ESLint
npm test             # Vitest
```

**Backend commands:**

```bash
pytest -x -v                          # unit tests
pytest -m "not slow" -x -v            # skip slow / RL tests
pytest -x -v tests/integration/       # integration tests
pytest -x -v tests/end_to_end/        # end-to-end tests
ruff format && ruff check             # format and lint
mypy .                                # type check
```

## Project Structure

```text
RL-Studio/
├── backend/
│   ├── main.py                 # Entrypoint
│   ├── api/                    # FastAPI app and routers
│   ├── ai/                     # Meta Model API adapter and registry
│   ├── environments/           # Warehouse env, config, fingerprints
│   ├── training/               # PPO training and callbacks
│   ├── studio/                 # Studio session, catalog, manager, controls
│   ├── verification/           # Verification engine, rules, workflow
│   ├── diagnosis/              # Incident detection, evidence, investigation
│   ├── recovery/               # Recovery planning and execution
│   ├── evaluation/             # Evidence-based evaluation
│   ├── provenance/             # Artifact provenance and incident sink
│   ├── projects/               # Project service, scope, documents
│   ├── assistant/              # Assistant and voice
│   ├── fault_injection/        # Controlled faults
│   └── workflow/               # Event-driven automation
├── frontend/
│   ├── src/
│   │   ├── pages/              # Training, Studio, Monitoring, Projects…
│   │   ├── features/           # Feature modules (verification, diagnosis…)
│   │   ├── components/         # Shared UI components
│   │   └── services/           # API clients
│   └── package.json
├── shared/                     # Contracts, events, schemas
├── tests/                      # Integration and end-to-end tests
├── scripts/                    # dev.sh, backend.sh, frontend.sh, helpers
├── requirements.txt
└── .env.example
```

## Contributing & License

See [CONTRIBUTING.md](CONTRIBUTING.md) for development conventions. Key points: always work on the `backend3` branch, use conventional commit messages (`feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`), run `ruff format`, `ruff check`, `mypy .`, and `pytest` before committing, and open pull requests from `backend3` to `main`.

See [SECURITY.md](SECURITY.md) for vulnerability reporting and security guidelines.

This software is proprietary. See [LICENSE](LICENSE) for the full proprietary license agreement. Usage, reproduction, modification, distribution, and commercialization require prior written authorization from Self-Healing RL Studio.
