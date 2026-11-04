/**
 * Training-history service: the project's persisted agents, environments, experiments and training runs.
 *
 * Binds `backend/api/routers/training_history.py` (`/api/v1/projects/{project_id}/...`). The project in the path is
 * authorised by the backend, which also hides another project's records behind the same 404; nothing here
 * filters by project on the client. Every call resolves a `ServiceResult`: a failed read never turns into an
 * empty list or an invented run.
 */
import { api } from './client'
import type { ServiceResult } from './types'
import { serviceError } from './types'

export type RunStatus =
  | 'queued'
  | 'initializing'
  | 'running'
  | 'paused'
  | 'stopping'
  | 'completed'
  | 'stopped'
  | 'failed'
  | 'interrupted'

export type TerminationReason =
  'natural_completion' | 'user_requested_stop' | 'training_failure' | 'unexpected_interruption'

export interface RunFinalMetrics {
  mean_reward?: number | null
  current_reward_avg?: number | null
  best_reward?: number | null
  success_rate?: number | null
  steps_per_second?: number | null
  fraction?: number | null
}

export interface TrainingRun {
  run_id: string
  project_id: string | null
  experiment_id: string | null
  experiment_name: string | null
  agent_id: string | null
  agent_name: string | null
  agent_version: number | null
  environment_config_id: string | null
  environment_config_name: string | null
  environment_config_version: number | null
  session_id: string | null
  name: string | null
  algorithm: string | null
  environment_name: string | null
  seed: number | null
  status: RunStatus
  termination_reason: TerminationReason | null
  continues_run_id: string | null
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  total_timesteps: number | null
  total_episodes: number | null
  final_metrics: RunFinalMetrics
  error: string | null
  active: boolean
}

export interface RunPage {
  total: number
  limit: number
  offset: number
  items: TrainingRun[]
}

export interface RunListQuery {
  agentId?: string
  environmentConfigId?: string
  experimentId?: string
  status?: string
  q?: string
  sort?: 'recent' | 'oldest' | 'timesteps'
  limit?: number
  offset?: number
}

export interface NamedEntity {
  id: string
  name: string
  version: number
  run_count: number
  latest_run_id: string | null
  algorithm?: string
}

export interface RunDetail {
  run: TrainingRun
  snapshots: {
    agent?: Record<string, unknown>
    environment?: Record<string, unknown>
    training?: Record<string, unknown>
  }
  checkpoints: Array<Record<string, unknown>>
  verifications: Array<{ verification_id: string; overall_status: string; created_at: string }>
  incidents: Array<{
    incident_id: string
    status: string
    severity: string | null
    summary: string | null
    created_at: string
    investigations: number
  }>
  recoveries: Array<{
    recovery_id: string
    incident_id: string
    recovery_status: string
    recovery_strategy: string
    created_at: string
  }>
}

export interface EpisodeRecord {
  episode?: number
  reward: number | null
  length?: number | null
  end_step?: number | null
  [key: string]: unknown
}

export interface RunMetrics {
  run_id: string
  status: RunStatus
  final_metrics: RunFinalMetrics
  total_timesteps: number | null
  total_episodes: number | null
  episodes_total: number
  available: boolean
  episodes: EpisodeRecord[]
  updates: Array<Record<string, unknown>>
  evaluations: Array<Record<string, unknown>>
}

export interface RunComparison {
  comparable: boolean
  reasons: string[]
  runs: TrainingRun[]
}

const seg = encodeURIComponent
const UNEXPECTED = 'The service returned an unexpected response.'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isRun(value: unknown): value is TrainingRun {
  return isRecord(value) && typeof value.run_id === 'string' && typeof value.status === 'string'
}

function queryString(query: RunListQuery): string {
  const params = new URLSearchParams()
  const map: Array<[string, string | number | undefined]> = [
    ['agent_id', query.agentId],
    ['environment_config_id', query.environmentConfigId],
    ['experiment_id', query.experimentId],
    ['status', query.status],
    ['q', query.q?.trim() || undefined],
    ['sort', query.sort],
    ['limit', query.limit],
    ['offset', query.offset],
  ]
  for (const [key, value] of map)
    if (value !== undefined && value !== '') params.set(key, String(value))
  const text = params.toString()
  return text === '' ? '' : `?${text}`
}

function entityList(key: string, idKey: string) {
  return (data: unknown): NamedEntity[] | null => {
    if (!isRecord(data) || !Array.isArray(data[key])) return null
    return (data[key] as Array<Record<string, unknown>>).map((e) => ({
      id: String(e[idKey]),
      name: String(e.name),
      version: Number(e.version ?? 1),
      run_count: Number(e.run_count ?? 0),
      latest_run_id: typeof e.latest_run_id === 'string' ? e.latest_run_id : null,
      algorithm: typeof e.algorithm === 'string' ? e.algorithm : undefined,
    }))
  }
}

export interface TrainingHistoryService {
  listRuns(
    projectId: string,
    query?: RunListQuery,
    signal?: AbortSignal,
  ): Promise<ServiceResult<RunPage>>
  latestRun(
    projectId: string,
    agentId?: string,
    signal?: AbortSignal,
  ): Promise<ServiceResult<TrainingRun | null>>
  getRun(projectId: string, runId: string, signal?: AbortSignal): Promise<ServiceResult<RunDetail>>
  getMetrics(
    projectId: string,
    runId: string,
    limit?: number,
    signal?: AbortSignal,
  ): Promise<ServiceResult<RunMetrics>>
  listAgents(projectId: string, signal?: AbortSignal): Promise<ServiceResult<NamedEntity[]>>
  listEnvironments(projectId: string, signal?: AbortSignal): Promise<ServiceResult<NamedEntity[]>>
  listExperiments(projectId: string, signal?: AbortSignal): Promise<ServiceResult<NamedEntity[]>>
  compare(
    projectId: string,
    runIds: string[],
    signal?: AbortSignal,
  ): Promise<ServiceResult<RunComparison>>
}

export function createTrainingHistoryService(): TrainingHistoryService {
  const base = (projectId: string) => `/api/v1/projects/${seg(projectId)}`

  async function entities(
    projectId: string,
    path: string,
    key: string,
    idKey: string,
    signal?: AbortSignal,
  ): Promise<ServiceResult<NamedEntity[]>> {
    const result = await api.get<unknown>(`${base(projectId)}/${path}`, { signal })
    if (result.state === 'error') return result
    const parsed = entityList(key, idKey)(result.data)
    return parsed === null ? serviceError('unexpected', UNEXPECTED) : { state: 'ok', data: parsed }
  }

  return {
    async listRuns(projectId, query = {}, signal) {
      const result = await api.get<unknown>(
        `${base(projectId)}/training-runs${queryString(query)}`,
        { signal },
      )
      if (result.state === 'error') return result
      const d = result.data
      if (
        !isRecord(d) ||
        !Array.isArray(d.items) ||
        !d.items.every(isRun) ||
        typeof d.total !== 'number'
      ) {
        return serviceError('unexpected', UNEXPECTED)
      }
      return { state: 'ok', data: d as unknown as RunPage }
    },
    async latestRun(projectId, agentId, signal) {
      const suffix = agentId ? `?agent_id=${seg(agentId)}` : ''
      const result = await api.get<unknown>(`${base(projectId)}/training-runs/latest${suffix}`, {
        signal,
      })
      if (result.state === 'error') return result
      const d = result.data
      if (!isRecord(d) || !('run' in d) || (d.run !== null && !isRun(d.run)))
        return serviceError('unexpected', UNEXPECTED)
      return { state: 'ok', data: d.run as TrainingRun | null }
    },
    async getRun(projectId, runId, signal) {
      const result = await api.get<unknown>(`${base(projectId)}/training-runs/${seg(runId)}`, {
        signal,
      })
      if (result.state === 'error') return result
      return isRecord(result.data) && isRun(result.data.run)
        ? { state: 'ok', data: result.data as unknown as RunDetail }
        : serviceError('unexpected', UNEXPECTED)
    },
    async getMetrics(projectId, runId, limit = 200, signal) {
      const result = await api.get<unknown>(
        `${base(projectId)}/training-runs/${seg(runId)}/metrics?limit=${limit}`,
        { signal },
      )
      if (result.state === 'error') return result
      return isRecord(result.data) && Array.isArray(result.data.episodes)
        ? { state: 'ok', data: result.data as unknown as RunMetrics }
        : serviceError('unexpected', UNEXPECTED)
    },
    listAgents: (projectId, signal) => entities(projectId, 'agents', 'agents', 'agent_id', signal),
    listEnvironments: (projectId, signal) =>
      entities(projectId, 'environments', 'environments', 'environment_config_id', signal),
    listExperiments: (projectId, signal) =>
      entities(projectId, 'experiments', 'experiments', 'experiment_id', signal),
    async compare(projectId, runIds, signal) {
      const result = await api.get<unknown>(
        `${base(projectId)}/training-runs/compare?run_ids=${seg(runIds.join(','))}`,
        { signal },
      )
      if (result.state === 'error') return result
      const d = result.data
      return isRecord(d) && typeof d.comparable === 'boolean' && Array.isArray(d.runs)
        ? { state: 'ok', data: d as unknown as RunComparison }
        : serviceError('unexpected', UNEXPECTED)
    },
  }
}
