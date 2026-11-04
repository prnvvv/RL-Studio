/**
 * A contract-level stand-in for the training-history endpoints (`/api/v1/projects/{id}/...`), for page and hook tests.
 *
 * It mirrors the real backend's contract, including the rule that matters most to the UI: a run that belongs to another
 * project answers 404 exactly like a missing one. The backend itself (real training, persistence, isolation) is
 * verified by `backend/training_history/tests`; this fake only lets the frontend be tested without a server, and it
 * never invents data: tests declare every run they want to exist.
 */
import { vi } from 'vitest'
import type { RunDetail, RunMetrics, TrainingRun } from '../services/trainingHistory'

export const PROJECT_A = 'prj_aaaaaaaaaaaaaaaa'
export const PROJECT_B = 'prj_bbbbbbbbbbbbbbbb'

export function makeRun(overrides: Partial<TrainingRun> & { run_id: string }): TrainingRun {
  return {
    project_id: PROJECT_A,
    experiment_id: null,
    experiment_name: null,
    agent_id: 'agt_000000000001',
    agent_name: 'PPO',
    agent_version: 1,
    environment_config_id: 'env_000000000001',
    environment_config_name: 'cartpole',
    environment_config_version: 1,
    session_id: 'ses_00000001',
    name: null,
    algorithm: 'PPO',
    environment_name: 'cartpole',
    seed: 7,
    status: 'completed',
    termination_reason: 'natural_completion',
    continues_run_id: null,
    started_at: '2026-11-01T10:00:00+00:00',
    finished_at: '2026-11-01T10:05:00+00:00',
    duration_seconds: 300,
    total_timesteps: 2000,
    total_episodes: 40,
    final_metrics: { mean_reward: 21.5, best_reward: 60, success_rate: 0.25 },
    error: null,
    active: false,
    ...overrides,
  }
}

export interface FakeDb {
  runs: TrainingRun[]
  details?: Record<string, Partial<RunDetail>>
  metrics?: Record<string, Partial<RunMetrics>>
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status })
}

/** Install a `fetch` that serves `db` through the documented routes. Returns the spy (call log included). */
export function installHistoryFake(db: FakeDb) {
  const spy = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')
    const projectOnly = url.pathname.match(/^\/api\/v1\/projects\/(prj_[0-9a-f]{16})$/)
    if (projectOnly) {
      // the shell's project chip reads the project record; both fake projects exist
      const id = projectOnly[1]
      return id === PROJECT_A || id === PROJECT_B
        ? json({
            project_id: id,
            name: id === PROJECT_A ? 'Alpha' : 'Beta',
            description: null,
            status: 'active',
            created_at: '2026-11-01T00:00:00+00:00',
            updated_at: '2026-11-01T00:00:00+00:00',
            agent: {},
            environment: {},
            training: { state: 'not_started' },
            counts: {},
          })
        : json({ error: { code: 'not_found' } }, 404)
    }
    const m = url.pathname.match(/^\/api\/v1\/projects\/(prj_[0-9a-f]{16})\/(.*)$/)
    if (!m) return json({ error: { code: 'not_found' } }, 404)
    const [, project, rest] = m
    const own = db.runs.filter((r) => r.project_id === project)
    if (rest === 'training-runs') {
      const q = url.searchParams
      let items = own
      const agent = q.get('agent_id')
      const status = q.get('status')
      const search = q.get('q')?.toLowerCase()
      if (agent) items = items.filter((r) => r.agent_id === agent)
      if (status) items = items.filter((r) => r.status === status)
      if (search)
        items = items.filter((r) =>
          `${r.run_id} ${r.agent_name} ${r.name}`.toLowerCase().includes(search),
        )
      items = [...items].sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))
      const limit = Number(q.get('limit') ?? 50)
      const offset = Number(q.get('offset') ?? 0)
      return json({
        total: items.length,
        limit,
        offset,
        items: items.slice(offset, offset + limit),
      })
    }
    if (rest === 'training-runs/latest') {
      const sorted = [...own].sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? ''))
      return json({ run: sorted[0] ?? null })
    }
    if (rest === 'agents' || rest === 'environments' || rest === 'experiments') {
      const ids = new Map<string, TrainingRun>()
      for (const r of own) if (r.agent_id) ids.set(r.agent_id, r)
      if (rest === 'agents') {
        return json({
          count: ids.size,
          agents: [...ids.values()].map((r) => ({
            agent_id: r.agent_id,
            name: r.agent_name,
            version: r.agent_version ?? 1,
            run_count: own.filter((x) => x.agent_id === r.agent_id).length,
            latest_run_id: r.run_id,
            algorithm: r.algorithm,
          })),
        })
      }
      return json({ count: 0, [rest]: [] })
    }
    const run = rest.match(/^training-runs\/([^/]+)(?:\/(metrics))?$/)
    if (run) {
      const found = own.find((r) => r.run_id === decodeURIComponent(run[1]))
      if (!found) return json({ error: { code: 'not_found' } }, 404) // missing and other-project look identical
      if (run[2] === 'metrics') {
        const extra = db.metrics?.[found.run_id] ?? {}
        return json({
          run_id: found.run_id,
          status: found.status,
          final_metrics: found.final_metrics,
          total_timesteps: found.total_timesteps,
          total_episodes: found.total_episodes,
          episodes_total: found.total_episodes ?? 0,
          available: true,
          episodes: [],
          updates: [],
          evaluations: [],
          ...extra,
        })
      }
      const extra = db.details?.[found.run_id] ?? {}
      return json({
        run: found,
        snapshots: {
          agent: { agent: found.algorithm, agent_params: { learning_rate: 0.0003 } },
          environment: { environment: found.environment_name, env_params: {} },
          training: {},
        },
        checkpoints: [],
        verifications: [],
        incidents: [],
        recoveries: [],
        ...extra,
      })
    }
    return json({ error: { code: 'not_found' } }, 404)
  })
  vi.stubGlobal('fetch', spy)
  return spy
}

/** Make `projectId` the active project the way the app persists it, before any provider mounts. */
export function activateProject(projectId: string): void {
  window.localStorage.setItem('rl-studio.activeProject', projectId)
}
