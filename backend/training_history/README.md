# Training history

The project-scoped, persistent record of every training run. It extends the existing Studio and provenance
architecture; it does not replace it.

```
Project -> Agent / Environment configuration (versioned) -> Experiment (optional) -> Training run
        -> metrics, episodes, checkpoints (Studio store) -> verification -> incidents -> diagnosis -> recovery
```

## Where things live

| Data | Stored in | Notes |
|---|---|---|
| Run catalog (`training_runs`) | main database (migration 6) | Authoritative: project, agent, environment, experiment, config **snapshots**, status, termination reason, totals, final metrics |
| Agents / environment configs / experiments | main database (migration 6) | Reused when a run's configuration matches; an explicit entity re-trained with a changed configuration gets a new `version` and keeps its earlier configuration in `revisions_json` |
| Episodes, steps, updates, evaluations, checkpoint files | Studio store (`studio.sqlite3`) and artifact storage | Referenced by `run_id`; trajectories are never part of a summary/detail response |
| Provenance run, events, incidents, recoveries, verification | existing tables | Linked by `run_id` / `incident_id` |

## Lifecycle (written by `TrainingSession` through `RunBridge`)

`register_run` (one transaction) -> `progress` (throttled, never lowers totals, never reopens a finished run) ->
`stopping` -> `finish`. The `runs.status` provenance row is updated at the end too (it used to stay `running`).

| Ended because | status | termination_reason |
|---|---|---|
| training reached its budget | `completed` | `natural_completion` |
| the user stopped it | `stopped` | `user_requested_stop` (never reported as completed) |
| the training raised | `failed` | `training_failure` (+ `error`) |
| the backend died / restarted | `interrupted` | `unexpected_interruption` |

On application start, any run still marked active that is not alive in this process is marked `interrupted` at its last
recorded progress (`reconcile`). It is never marked completed.

## Isolation

`/api/v1/projects/{project_id}/...` (`backend/api/routers/training_history.py`): the project must exist, a scope header
naming another project is refused, every lookup is filtered by the project, and a missing record and another project's
record give the identical 404. Starting training with an `agent_id`, `environment_config_id`, `experiment_id` or
`continues_run_id` that is not the project's is refused before a session exists. Runs without a project (legacy) are never
assigned to one automatically.

## API

Agents, environments, experiments (list/create/rename), `GET .../training-runs` (filters: agent, environment,
experiment, status, search; sort; paginated, page size <= 200), `.../training-runs/latest`, `.../compare`,
`.../training-runs/{run_id}` (detail: snapshots, checkpoints, verifications, incidents, recoveries),
`.../metrics`, `.../events`, `.../checkpoints`.

## Frontend

`useSelectedRun` (URL `?runId=` -> remembered selection -> latest run) feeds `RunContextBar` on Monitoring, Reports,
Diagnosis and the project workspace; `TrainingHistoryPanel` is the history table (workspace page).

## Known limits

See the final report of the change that introduced this module: no browser (Playwright) workflow exists in the repo,
Studio's own configuration UI does not yet pick a saved agent/environment, and run comparison is limited to the
recorded final metrics of runs on the same environment.
