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
  UploadedEnvironment,
  UploadedModel,
} from '../features/studio/studioTypes'
import type { ServiceResult } from './types'
import { serviceError } from './types'
import { api, buildRequestUrl, kindForStatus, MESSAGES } from './client'

const BASE = '/api/v1/studio'

export interface CreateSessionRequest extends SessionConfig {
  name?: string
}

export type SessionCommand = 'start' | 'pause' | 'resume' | 'stop' | 'reset'

/** `uploading` while bytes are sent; `validating` while the backend inspects the file. */
export type UploadPhase = 'uploading' | 'validating'

export interface UploadOptions {
  name?: string
  signal?: AbortSignal
  onPhase?: (phase: UploadPhase) => void
  /** Fraction (0..1) of the request body sent so far. */
  onProgress?: (fraction: number) => void
}

export interface ModelUploadResult {
  model: UploadedModel
  /** True when identical bytes were already in the library. */
  duplicate: boolean
}

export interface EnvironmentUploadResult {
  environment: UploadedEnvironment
  duplicate: boolean
}

const UPLOAD_TIMEOUT_MS = 120_000
/** Mirrors the backend limit so an oversized layout is refused before it is sent. */
export const MAX_LAYOUT_BYTES = 64 * 1024
const MAX_DETAIL_CHARS = 300

function apiBase(): string {
  return import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, '') ?? ''
}

/**
 * Pull the backend's validation message out of an error body. Upload rejections
 * ("expects 4 observation values", "pickle files are not accepted") are written
 * by the backend as user-safe text, so for 4xx responses only we show that text
 * (length-limited, rendered as plain text). 5xx responses stay generic.
 */
export function uploadErrorMessage(status: number, body: unknown): string {
  const kind = kindForStatus(status)
  if (status >= 500 || !isObject(body) || !isObject(body.error)) return MESSAGES[kind]
  const error = body.error
  const details = isObject(error.details) ? error.details : null
  const first = details && Array.isArray(details.errors) ? details.errors[0] : null
  const text = isObject(first) && typeof first.message === 'string' ? first.message : error.message
  return typeof text === 'string' && text.trim() !== ''
    ? text.trim().slice(0, MAX_DETAIL_CHARS)
    : MESSAGES[kind]
}

function xhrUpload(
  path: string,
  body: Blob | string,
  contentType: string,
  options: UploadOptions,
): Promise<ServiceResult<unknown>> {
  return new Promise((resolve) => {
    if (options.signal?.aborted) return resolve(serviceError('cancelled', MESSAGES.cancelled))
    const xhr = new XMLHttpRequest()
    xhr.open('POST', buildRequestUrl(apiBase(), path))
    xhr.timeout = UPLOAD_TIMEOUT_MS
    xhr.setRequestHeader('Content-Type', contentType)
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0)
        options.onProgress?.(event.loaded / event.total)
    }
    xhr.upload.onload = () => options.onPhase?.('validating')
    const onAbort = () => xhr.abort()
    options.signal?.addEventListener('abort', onAbort)
    const done = (result: ServiceResult<unknown>) => {
      options.signal?.removeEventListener('abort', onAbort)
      resolve(result)
    }
    xhr.onload = () => {
      let parsed: unknown = null
      try {
        parsed = xhr.responseText ? (JSON.parse(xhr.responseText) as unknown) : null
      } catch {
        parsed = null
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        return done(
          parsed === null
            ? serviceError('unexpected', MESSAGES.unexpected, xhr.status)
            : { state: 'ok', data: parsed },
        )
      }
      done(
        serviceError(kindForStatus(xhr.status), uploadErrorMessage(xhr.status, parsed), xhr.status),
      )
    }
    xhr.onerror = () => done(serviceError('network', MESSAGES.network))
    xhr.ontimeout = () => done(serviceError('timeout', MESSAGES.timeout))
    xhr.onabort = () => done(serviceError('cancelled', MESSAGES.cancelled))
    options.onPhase?.('uploading')
    xhr.send(body)
  })
}

function isModelUpload(value: unknown): value is ModelUploadResult {
  return (
    isObject(value) &&
    isObject(value.model) &&
    typeof value.model.key === 'string' &&
    typeof value.duplicate === 'boolean'
  )
}

function isEnvironmentUpload(value: unknown): value is EnvironmentUploadResult {
  return (
    isObject(value) &&
    isObject(value.environment) &&
    typeof value.environment.key === 'string' &&
    typeof value.duplicate === 'boolean'
  )
}

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
  return isObject(value) && typeof value.session_id === 'string' && typeof value.status === 'string'
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
  setControl(sessionId: string, active: boolean): Promise<ServiceResult<CommandResult>>
  listSessions(signal?: AbortSignal): Promise<ServiceResult<SessionSummary[]>>
  listHistory(signal?: AbortSignal): Promise<ServiceResult<ExperimentSummary[]>>
  getHistoryRecord(runId: string, signal?: AbortSignal): Promise<ServiceResult<SessionSnapshot>>
  uploadModel(file: File, options?: UploadOptions): Promise<ServiceResult<ModelUploadResult>>
  uploadEnvironment(
    file: File,
    options?: UploadOptions,
  ): Promise<ServiceResult<EnvironmentUploadResult>>
  deleteModel(modelId: string): Promise<ServiceResult<unknown>>
  deleteEnvironment(envId: string): Promise<ServiceResult<unknown>>
}

/** Download URL for a run's full step-level trajectory (newline-delimited JSON). */
export function runExportUrl(runId: string): string {
  return buildRequestUrl(apiBase(), `${BASE}/runs/${encodeURIComponent(runId)}/export`)
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
      return guard(await api.post<unknown>(`${BASE}/sessions`, { jsonBody: request }), isSnapshot)
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
    async setControl(sessionId, active) {
      return guard(
        await api.post<unknown>(`${BASE}/sessions/${encodeURIComponent(sessionId)}/control`, {
          jsonBody: { active },
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
    async uploadModel(file, options = {}) {
      const query = new URLSearchParams({ filename: file.name })
      if (options.name) query.set('name', options.name)
      const result = await xhrUpload(
        `${BASE}/models/upload?${query}`,
        file,
        'application/octet-stream',
        options,
      )
      return guard(result, isModelUpload)
    },
    async uploadEnvironment(file, options = {}) {
      if (file.size > MAX_LAYOUT_BYTES) {
        return serviceError(
          'invalid_request',
          `A layout file must be smaller than ${MAX_LAYOUT_BYTES / 1024} KB.`,
        )
      }
      const text = await file.text()
      return guard(
        await xhrUpload(`${BASE}/environments/upload`, text, 'application/json', options),
        isEnvironmentUpload,
      )
    },
    async deleteModel(modelId) {
      return api.request<unknown>(`${BASE}/models/${encodeURIComponent(modelId)}`, {
        method: 'DELETE',
      })
    },
    async deleteEnvironment(envId) {
      return api.request<unknown>(`${BASE}/environments/${encodeURIComponent(envId)}`, {
        method: 'DELETE',
      })
    },
  }
}
