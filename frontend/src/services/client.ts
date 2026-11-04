/**
 * Central HTTP client for the Self-Healing RL Studio API.
 *
 * Single place that owns:
 * - base URL resolution (`VITE_API_BASE_URL`; empty = same origin),
 * - JSON serialization and Accept negotiation,
 * - bounded per-request timeouts,
 * - cancellation propagation,
 * - mapping of every failure mode onto the stable `ServiceResult` contract.
 *
 * Page and feature code must use domain services built on this client, and
 * must not reimplement HTTP behaviour or call `fetch` directly.
 *
 * Failure messages are generic per category and safe to show verbatim in the
 * UI: raw response bodies, headers, stack traces, and backend internals are
 * never surfaced (frontend/AGENTS.md §10.4, §19).
 */
import { projectScopeHeaders } from './projectScope'
import type { ServiceErrorKind, ServiceResult } from './types'

const DEFAULT_TIMEOUT_MS = 10_000

export interface ApiClientConfig {
  /** Base URL such as "http://localhost:8000"; empty string = same origin. */
  baseUrl?: string
  /** Per-request timeout in milliseconds. Default 10 s. */
  timeoutMs?: number
}

interface RequestOptions extends Omit<RequestInit, 'signal' | 'body'> {
  /** Serializable JSON body; implies a JSON Content-Type. */
  jsonBody?: unknown
  /** Optional caller-owned cancellation signal. */
  signal?: AbortSignal
  /** Overrides the client timeout for slow operations (model calls, policy rollouts). */
  timeoutMs?: number
}

/**
 * Build the base URL once from the environment. An unset variable means the
 * API is served from the same origin (empty string).
 */
function resolveBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, '') ?? ''
}

/**
 * Compose the absolute request URL. `path` must start with "/" and may
 * include a query. Trailing slashes on the base URL are tolerated, so a
 * configuration of "http://host:8000/" and "http://host:8000" behave the same.
 */
export function buildRequestUrl(baseUrl: string, path: string): string {
  if (!path.startsWith('/')) {
    throw new Error(`API request path must start with "/": ${path}`)
  }
  const normalizedBase = baseUrl.replace(/\/+$/, '')
  return `${normalizedBase}${path}`
}

/** Map an HTTP status onto a stable, UI-presentable error kind. */
export function kindForStatus(status: number): ServiceErrorKind {
  if (status === 400 || status === 422) return 'invalid_request'
  if (status === 401 || status === 403) return 'unauthorized'
  if (status === 404) return 'not_found'
  if (status === 409) return 'conflict'
  if (status === 429) return 'rate_limited'
  if (status === 503) return 'unavailable'
  if (status >= 500) return 'server_error'
  return 'unexpected'
}

export const MESSAGES: Record<ServiceErrorKind, string> = {
  invalid_request: 'The request was rejected as invalid.',
  unauthorized: 'You are not authorized to perform this action.',
  not_found: 'The requested record was not found.',
  conflict: 'The recorded state does not allow this action.',
  rate_limited: 'Too many requests; try again shortly.',
  unavailable: 'The service is currently unavailable.',
  server_error: 'The service encountered an internal error.',
  timeout: 'The request timed out; the backend operation state is unknown.',
  network: 'The service could not be reached; any pending operation state is unknown.',
  cancelled: 'The request was cancelled.',
  unexpected: 'The service returned an unexpected response.',
}

function errorResult(
  kind: ServiceErrorKind,
  status?: number,
  extra: { code?: string; detail?: string } = {},
): ServiceResult<never> {
  return {
    state: 'error',
    error: {
      kind,
      message: MESSAGES[kind],
      ...(status !== undefined ? { status } : {}),
      ...(extra.code !== undefined ? { code: extra.code } : {}),
      ...(extra.detail !== undefined ? { detail: extra.detail } : {}),
    },
  }
}

const MAX_DETAIL = 300

/**
 * The backend's sanitized `{"error": {"code", "message"}}` body (also nested under FastAPI's `detail`). Only short
 * strings from that exact shape are surfaced; any other body is ignored so raw exception text can never leak.
 */
export function backendErrorDetail(text: string): { code?: string; detail?: string } {
  try {
    const body = JSON.parse(text) as { error?: unknown; detail?: { error?: unknown } }
    const error = (body.error ?? body.detail?.error) as
      { code?: unknown; message?: unknown } | undefined
    if (typeof error !== 'object' || error === null) return {}
    const out: { code?: string; detail?: string } = {}
    if (typeof error.code === 'string' && error.code.length <= 64) out.code = error.code
    // The message is only surfaced alongside a stable code: an uncoded body is never shown.
    if (
      out.code !== undefined &&
      typeof error.message === 'string' &&
      error.message.trim() !== ''
    ) {
      out.detail = error.message.slice(0, MAX_DETAIL)
    }
    return out
  } catch {
    return {}
  }
}

/**
 * Stable "record does not exist" result for mock adapters and planned
 * endpoints whose lookup table legitimately cannot contain the requested id.
 * Keeps the message identical to the client's mapped `not_found` phrasing.
 */
export function recordNotFound<T>(): ServiceResult<T> {
  return errorResult('not_found')
}

/**
 * Create an API client. Tests inject `baseUrl` and mock `fetch` directly;
 * production code uses the `api` singleton unless a different target exists.
 */
export function createApiClient(config: ApiClientConfig = {}) {
  const baseUrl = config.baseUrl ?? resolveBaseUrl()
  const clientTimeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS

  async function request<T>(path: string, options: RequestOptions = {}): Promise<ServiceResult<T>> {
    const { jsonBody, headers, signal, timeoutMs: requestTimeoutMs, ...rest } = options
    const timeoutMs = requestTimeoutMs ?? clientTimeoutMs

    if (signal?.aborted) {
      return errorResult('cancelled')
    }

    // One controller owns both the caller signal and the timeout so that a
    // hung request fails into `timeout` rather than waiting forever, while an
    // external abort is still reported as `cancelled`.
    const controller = new AbortController()
    let timedOut = false
    const timer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, timeoutMs)
    const onExternalAbort = () => controller.abort()
    signal?.addEventListener('abort', onExternalAbort)

    const requestHeaders = new Headers(headers)
    // The open project travels with every request; the backend enforces the isolation.
    for (const [name, value] of Object.entries(projectScopeHeaders())) {
      if (!requestHeaders.has(name)) requestHeaders.set(name, value)
    }
    if (jsonBody !== undefined && !requestHeaders.has('Content-Type')) {
      requestHeaders.set('Content-Type', 'application/json')
    }
    if (!requestHeaders.has('Accept')) {
      requestHeaders.set('Accept', 'application/json')
    }

    try {
      const response = await fetch(buildRequestUrl(baseUrl, path), {
        ...rest,
        headers: requestHeaders,
        body: jsonBody === undefined ? undefined : JSON.stringify(jsonBody),
        signal: controller.signal,
      })

      if (!response.ok) {
        const body = await response.text().catch(() => '')
        return errorResult(
          kindForStatus(response.status),
          response.status,
          backendErrorDetail(body),
        )
      }

      if (response.status === 204) {
        // No content: represent honestly as null rather than inventing a body.
        return { state: 'ok', data: null as T }
      }

      const text = await response.text()
      if (!text) {
        return { state: 'ok', data: null as T }
      }
      try {
        return { state: 'ok', data: JSON.parse(text) as T }
      } catch {
        // A 2xx response with a non-JSON body is an unexpected contract break.
        return errorResult('unexpected', response.status)
      }
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') {
        return errorResult(timedOut ? 'timeout' : 'cancelled')
      }
      // fetch rejects with TypeError for unreachable hosts and DNS failures.
      return errorResult('network')
    } finally {
      clearTimeout(timer)
      signal?.removeEventListener('abort', onExternalAbort)
    }
  }

  function get<T>(path: string, options: RequestOptions = {}): Promise<ServiceResult<T>> {
    return request<T>(path, { ...options, method: options.method ?? 'GET' })
  }

  function post<T>(path: string, options: RequestOptions = {}): Promise<ServiceResult<T>> {
    return request<T>(path, { ...options, method: options.method ?? 'POST' })
  }

  return { request, get, post }
}

/** Default client used by domain services. */
export const api = createApiClient()
