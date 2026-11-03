/**
 * Studio service: catalog, session lifecycle, experiment history.
 *
 * Binds `backend/api/routers/studio.py`. Every call resolves a
 * `ServiceResult`; nothing here invents data when the backend is unreachable.
 */
import type {
  Catalog,
  CommandResult,
  ExperimentSummary,
  SessionConfig,
  SessionSnapshot,
  SessionSummary,
} from '../features/studio/studioTypes'
import type { ServiceResult } from './types'
import { serviceError } from './types'
import { api } from './client'

const BASE = '/api/v1/studio'

export interface CreateSessionRequest extends SessionConfig {
  name?: string
}

export type SessionCommand = 'start' | 'pause' | 'resume' | 'stop' | 'reset'

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isCatalog(value: unknown): value is Catalog {
  return (
    isObject(value) &&
    Array.isArray(value.agents) &&
    Array.isArray(value.environments) &&
    Array.isArray(value.training_params)
  )
}

function isSnapshot(value: unknown): value is SessionSnapshot {
  return (
    isObject(value) &&
    typeof value.session_id === 'string' &&
    typeof value.status === 'string' &&
    isObject(value.config) &&
    isObject(value.progress)
  )
}

function isCommandResult(value: unknown): value is CommandResult {
  return (
    isObject(value) && typeof value.session_id === 'string' && typeof value.status === 'string'
  )
}

function guard<T>(
  result: ServiceResult<unknown>,
  check: (value: unknown) => value is T,
): ServiceResult<T> {
  if (result.state === 'error') return result
  if (!check(result.data)) {
    return serviceError('unexpected', 'The service returned an unexpected response.')
  }
  return { state: 'ok', data: result.data }
}

export interface StudioService {
  getCatalog(signal?: AbortSignal): Promise<ServiceResult<Catalog>>
  createSession(request: CreateSessionRequest): Promise<ServiceResult<SessionSnapshot>>
  getSession(sessionId: string, signal?: AbortSignal): Promise<ServiceResult<SessionSnapshot>>
  command(sessionId: string, command: SessionCommand): Promise<ServiceResult<CommandResult>>
  setSpeed(sessionId: string, speed: number): Promise<ServiceResult<CommandResult>>
  listSessions(signal?: AbortSignal): Promise<ServiceResult<SessionSummary[]>>
  listHistory(signal?: AbortSignal): Promise<ServiceResult<ExperimentSummary[]>>
  getHistoryRecord(runId: string, signal?: AbortSignal): Promise<ServiceResult<SessionSnapshot>>
}

export function sessionStreamUrl(sessionId: string, after = 0): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, '') ?? ''
  const origin =
    configured !== ''
      ? configured.replace(/^http/, 'ws')
      : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
  return `${origin}${BASE}/sessions/${encodeURIComponent(sessionId)}/stream?after=${after}`
}

export function createStudioService(): StudioService {
  return {
    async getCatalog(signal) {
      return guard(await api.get<unknown>(`${BASE}/catalog`, { signal }), isCatalog)
    },
    async createSession(request) {
      return guard(
        await api.post<unknown>(`${BASE}/sessions`, { jsonBody: request }),
        isSnapshot,
      )
    },
    async getSession(sessionId, signal) {
      return guard(
        await api.get<unknown>(`${BASE}/sessions/${encodeURIComponent(sessionId)}`, { signal }),
        isSnapshot,
      )
    },
    async command(sessionId, command) {
      return guard(
        await api.post<unknown>(`${BASE}/sessions/${encodeURIComponent(sessionId)}/${command}`),
        isCommandResult,
      )
    },
    async setSpeed(sessionId, speed) {
      return guard(
        await api.post<unknown>(`${BASE}/sessions/${encodeURIComponent(sessionId)}/speed`, {
          jsonBody: { speed },
        }),
        isCommandResult,
      )
    },
    async listSessions(signal) {
      const result = await api.get<unknown>(`${BASE}/sessions`, { signal })
      if (result.state === 'error') return result
      if (!isObject(result.data) || !Array.isArray(result.data.sessions)) {
        return serviceError('unexpected', 'The service returned an unexpected response.')
      }
      return { state: 'ok', data: result.data.sessions as SessionSummary[] }
    },
    async listHistory(signal) {
      const result = await api.get<unknown>(`${BASE}/history`, { signal })
      if (result.state === 'error') return result
      if (!isObject(result.data) || !Array.isArray(result.data.experiments)) {
        return serviceError('unexpected', 'The service returned an unexpected response.')
      }
      return { state: 'ok', data: result.data.experiments as ExperimentSummary[] }
    },
    async getHistoryRecord(runId, signal) {
      return guard(
        await api.get<unknown>(`${BASE}/history/${encodeURIComponent(runId)}`, { signal }),
        isSnapshot,
      )
    },
  }
}
