# Project management: changes to files owned by other people

This lists every change the project-management work made to code owned by someone else, what interface it touches,
and what it was checked against. **No owner has approved any of these changes.** Each row says who needs to review
it; nothing below should be read as approval.

Ownership follows `backend/AGENTS.md` (P1 `frontend/`, P2 events/Studio, P3 `backend/verification/`,
`backend/diagnosis/`, P4 `backend/database/`, `backend/provenance/`, `backend/recovery/`, `backend/evaluation/`).

## Person 4: database (`backend/database/migrations.py`)

| Change | Interface | Compatibility check |
| --- | --- | --- |
| Migration 3 `project_management` | Adds `projects`, `project_documents`, `project_intent_links`, `project_requirement_links`, `project_run_bindings`, `project_run_verifications`, and index `idx_runs_project` on the existing `runs(project_id)` | `test_migration_additivity.py`: only `CREATE ... IF NOT EXISTS`; no existing table redefined, no column added/removed/retyped, existing rows byte-identical after upgrade, idempotent re-run |
| Migration 4 `project_requirement_policies` | Adds one table (the user's explicit critical-safety flag) | same |

* The run to project association reuses Person 4's existing `runs.project_id` column. Nothing was added to `runs`.
* Deleting a project is a soft delete (`projects.status = 'deleted'`). No run, event, artifact, incident or audit row is
  deleted or rewritten. The audit table stays append-only (tested).
* `backend/database/tests/test_foundation.py`: the expected migration list changed from `[1, 2]` to `[1, 2, 3, 4]`.
* **Needs P4 review:** migration numbering (3, 4), the new table names, and that `idx_runs_project` is acceptable.

## Person 2: Studio session / provenance bridge

| File | Change |
| --- | --- |
| `backend/studio/session.py` | `TrainingSession(..., project_id=None)`: optional, stored as an attribute, passed to the bridge, included in `summary()`. Deliberately **not** put in `config`, so stored configs and fingerprints are unchanged |
| `backend/studio/provenance_bridge.py` | `RunBridge(..., project_id=None)` passes it to `RunRegistration.project_id` (an existing Person 4 field) |
| `backend/studio/manager.py` | `create(raw, name, project_id=None)` |
| `backend/api/routers/studio.py` | optional `project_id` in the session request (must equal the request's project scope); Studio history and session lists are filtered by scope |

* `backend/studio/tests/test_project_compat.py` (two real short runs, one legacy and one in a project): identical agent
  config fingerprint, environment id/version, canonical event types, artifact counts and stored config; the event
  contract has no new field; `summary()` gains exactly one key.
* **Needs P2 review:** the new optional constructor parameters and the list filtering in the Studio router.

## Person 3: verification (`backend/verification/`)

| File | Change |
| --- | --- |
| `lifecycle/service.py` | `scope_resolver` hook so a requirement can be proposed/confirmed against a project before any run; `execute(..., finality=)`; `handoff(..., promote=)`; `promote_interim()`; new link statuses `created_interim`, `deferred_interim` |
| `lifecycle/graphs.py` | carries `finality` through the execution graph; final idempotency keys are unchanged |
| `storage/sqlite_store.py` | `interim_incidents()` query |
| `intent/requirement_validation.py` | validation severity order is now invalid > needs_clarification > not_evaluable, so a threshold the user must state is not hidden behind missing evidence |

* Final verification behaviour is unchanged: every mandatory FAIL/ERROR still registers an incident through Person 4.
  Deterministic verdicts are untouched; no model is involved in any of this.
* Interim policy: results taken while a run is still training are persisted, but their failures are deferred (not
  registered). Only a failed requirement the user explicitly flagged `critical_safety` raises an incident immediately,
  or the user promotes one. A promotion or the final handoff joins an existing interim incident for the failures it
  covers; only the not-yet-covered remainder becomes a new incident.
* **Needs P3 review:** all of the above, especially the validation-severity change and the new link statuses.
* **Needs P4 awareness:** interim incidents carry `details.provisional = true` and `details.finality = "interim"`.

## Person 4: API surface (`backend/api/`)

* `app.py` adds one router-level dependency (`backend/projects/scope.py`) to the provenance, recovery, evaluation,
  verification, runs, realtime and Studio routers. It adds no parameter to the documented OpenAPI schema (the
  documented-endpoint test is unchanged). The projects API is mounted `include_in_schema=False`.
* Request scoping: `X-Project-ID` header, or `?project_id=` for WebSocket/SSE. A record owned by one project (or
  unassigned/legacy) is invisible, with an identical 404, to any other scope. Unscoped requests see only legacy records.
* **Needs P4 review:** that the guard's id to run resolution (incident, artifact, evaluation) matches their tables.

## Person 1: frontend

| File | Change |
| --- | --- |
| `components/layout/TopNavigation.tsx` | new first item **Projects** (`/projects`), and the active-project chip. Existing items, routes, active-state rules, narrow-width menu and theme toggle are unchanged |
| `features/landing/LandingHero.tsx` | the "Open Studio" button now goes to `/projects` |
| `pages/HomePage.tsx`, `features/landing/LandingBackdrop.tsx` | the landing background moved into a shared component (rendered identically) so the Project Dashboard reuses it |
| `app/router.tsx`, `app/App.tsx` | `/projects`, `/projects/:projectId`; the active-project provider; pages remount when the project changes |
| `services/client.ts`, `events.ts`, `studio.ts` | the open project is sent on every request and stream |
| `features/studio/useStudioSession.ts` | sends the active project when creating a session |

* `TopNavigation.test.tsx`: Projects is present in both layouts; active on `/projects` and `/projects/:id` only; the
  existing Studio/Training/Monitoring active-state tests pass unchanged.
* **Needs P1 review:** the navigation item and chip, the landing CTA target, and the remount-on-switch behaviour.

## Dependency

* `requirements.txt`: `pypdf==6.21.4` (PDF text extraction). Pure Python, one transitive dependency
  (`typing_extensions`, already pinned). Needs the dependency owner's approval.

## Known gaps (not hidden)

* There is no Riffs module in this repository, so nothing was scoped for it.
* Legacy runs (created before projects) are visible only when no project is open, and can be adopted into a project
  explicitly. They are never reassigned automatically.
* A project's own management API (`/api/v1/projects/...`) is authorised by the path project id, not by the scope
  header, so the dashboard can manage any listed project while another is open. Run data is always scope-checked.
* `POST /api/v1/runs/start` is an existing stub that queues a run id without creating a run record, so it cannot be
  attributed to a project and is not scope-checked.
* The project guard cannot attribute a run whose provenance registration failed (no `runs` row); such a run is
  treated as legacy.
