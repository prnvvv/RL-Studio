/**
 * Canonical service-result contract shared by every domain service.
 *
 * Domain services never throw for expected failure categories: they resolve a
 * discriminated union so panels can render `loading / ok / error` without
 * try/catch at the component boundary. Unknown or worse-than-expected shapes
 * remain errors — the frontend never converts an unexpected payload into
 * plausible-looking data.
 */

/**
 * Stable error categories, aligned with `frontend/AGENTS.md` §10.4.
 *
 * `timeout` and `network` are deliberately distinct from "operation failed":
 * a lost request does not prove the backend operation failed or stopped, and
 * UI copy built on these kinds must not claim otherwise.
 */
export type ServiceErrorKind =
  /** 400/422 — request failed backend validation. */
  | 'invalid_request'
  /** 401/403 — authentication or authorization problem. */
  | 'unauthorized'
  /** 404 — the addressed resource does not exist. */
  | 'not_found'
  /** 409 — duplicated or illegal state transition. */
  | 'conflict'
  /** 429 — rate limited. */
  | 'rate_limited'
  /** 503 — a dependency is unavailable. */
  | 'unavailable'
  /** Other 5xx — backend failure. */
  | 'server_error'
  /** The client gave up waiting; backend operation state is unknown. */
  | 'timeout'
  /** The request never reached a server; backend operation state is unknown. */
  | 'network'
  /** The caller aborted the request. No operation outcome is implied. */
  | 'cancelled'
  /** Empty, non-JSON, or structurally invalid response. */
  | 'unexpected'

export interface ServiceError {
  kind: ServiceErrorKind
  /**
   * Non-sensitive message safe to display directly. Never raw backend
   * exception text, stack traces, headers, or internal paths.
   */
  message: string
  /** HTTP status when the failure came from a response. */
  status?: number
}

export type ServiceResult<T> = { state: 'ok'; data: T } | { state: 'error'; error: ServiceError }

/** Construct a caller-friendly error result. */
export function serviceError(
  kind: ServiceErrorKind,
  message: string,
  status?: number,
): ServiceResult<never> {
  return {
    state: 'error',
    error: status === undefined ? { kind, message } : { kind, message, status },
  }
}
