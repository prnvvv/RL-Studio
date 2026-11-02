/**
 * Run lifecycle — PROVISIONAL contract for Person 2's operational endpoints.
 *
 * Mirrors the mounted-but-undocumented `backend/api/routers/runs.py`
 * (`include_in_schema=False`) and `backend/workers/training_worker.py`:
 *
 * - `POST /api/v1/runs/start`          -> { run_id, status: "queued" }
 * - `POST /api/v1/runs/{run_id}/stop`  -> { run_id, status: "stop_requested", idempotent: true }
 * - `GET  /api/v1/runs/{run_id}/status` -> { run_id, status, error? }
 *
 * Person 2 has not agreed a canonical run-lifecycle payload yet, and the worker
 * currently reports a non-canonical subset (`running`, `completed`, `failed`,
 * `unknown`). This module therefore:
 *
 * - accepts only the fields the endpoints actually return;
 * - maps them onto the canonical lifecycle from root `AGENTS.md` §9;
 * - keeps the raw backend value and reports unrecognised values verbatim
 *   instead of coercing them into a plausible lifecycle state;
 * - never derives a terminal state from a transport failure.
 *
 * The status endpoint carries no metrics, timestamps, or stage information, so
 * nothing beyond the lifecycle state is inferred here.
 */

/** Canonical lifecycle states from root `AGENTS.md` §9. */
export const CANONICAL_RUN_STATES = [
  'created',
  'queued',
  'starting',
  'running',
  'stop_requested',
  'stopped',
  'completed',
  'failed',
  'cancelled',
] as const

export type CanonicalRunState = (typeof CANONICAL_RUN_STATES)[number]

/**
 * `unknown` is the backend's explicit "no recorded worker result for this run
 * id" answer. `unrecognized` is any other value: it is preserved and shown as
 * reported, never mapped onto a lifecycle state.
 */
export type RunLifecycleState = CanonicalRunState | 'unknown' | 'unrecognized'

/** Wire shape of `GET /api/v1/runs/{run_id}/status` as implemented today. */
export interface RunStatusPayload {
  run_id: string
  status: string
  /** Worker failure text. Never rendered verbatim; it may contain internals. */
  error?: string | null
}

/** Wire shape of `POST /api/v1/runs/{run_id}/stop`. */
export interface RunStopPayload {
  run_id: string
  status: string
  idempotent?: boolean
}

/** Wire shape of `POST /api/v1/runs/start`. */
export interface RunStartPayload {
  run_id: string
  status: string
}

/** Only field the start endpoint reads; the rest of its config is untyped. */
export interface RunStartRequest {
  run_id: string
}

export interface RunLifecycle {
  runId: string
  state: RunLifecycleState
  /** Backend value exactly as reported, retained for honest display. */
  rawStatus: string
  /**
   * True when the worker reported a failure. The failure text itself is not
   * surfaced because it is unbounded backend output (`frontend/AGENTS.md`
   * §10.4).
   */
  failureReported: boolean
}

export const TERMINAL_RUN_STATES: readonly CanonicalRunState[] = [
  'stopped',
  'completed',
  'failed',
  'cancelled',
]

/** States in which a stop request is meaningful. */
const ACTIVE_RUN_STATES: readonly CanonicalRunState[] = [
  'queued',
  'starting',
  'running',
  'stop_requested',
]

export function isCanonicalRunState(value: string): value is CanonicalRunState {
  return (CANONICAL_RUN_STATES as readonly string[]).includes(value)
}

/** True only for states the canonical lifecycle defines as terminal. */
export function isTerminalRunState(state: RunLifecycleState): boolean {
  return state !== 'unknown' && state !== 'unrecognized' && TERMINAL_RUN_STATES.includes(state)
}

/** True for queued/starting/running/stop_requested. Unknown is not "active". */
export function isActiveRunState(state: RunLifecycleState): boolean {
  return state !== 'unknown' && state !== 'unrecognized' && ACTIVE_RUN_STATES.includes(state)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim() !== ''
}

/**
 * Validate the status payload at the service boundary. Returns `null` for any
 * shape the endpoint was not documented to produce so callers can report an
 * unexpected response rather than render guessed values.
 */
export function parseRunStatusPayload(value: unknown): RunStatusPayload | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  if (!isNonEmptyString(record.run_id) || !isNonEmptyString(record.status)) return null
  if (record.error !== undefined && record.error !== null && typeof record.error !== 'string') {
    return null
  }
  return {
    run_id: record.run_id,
    status: record.status,
    ...(typeof record.error === 'string' ? { error: record.error } : {}),
  }
}

/** Validate the stop payload. `idempotent` is optional in the response. */
export function parseRunStopPayload(value: unknown): RunStopPayload | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  if (!isNonEmptyString(record.run_id) || !isNonEmptyString(record.status)) return null
  if (record.idempotent !== undefined && typeof record.idempotent !== 'boolean') return null
  return {
    run_id: record.run_id,
    status: record.status,
    ...(typeof record.idempotent === 'boolean' ? { idempotent: record.idempotent } : {}),
  }
}

/** Validate the start payload. */
export function parseRunStartPayload(value: unknown): RunStartPayload | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>
  if (!isNonEmptyString(record.run_id) || !isNonEmptyString(record.status)) return null
  return { run_id: record.run_id, status: record.status }
}

/** Map a raw backend status string onto the lifecycle without coercing it. */
export function toRunLifecycleState(rawStatus: string): RunLifecycleState {
  const normalized = rawStatus.trim()
  if (isCanonicalRunState(normalized)) return normalized
  if (normalized === 'unknown') return 'unknown'
  return 'unrecognized'
}

export function toRunLifecycle(payload: RunStatusPayload): RunLifecycle {
  return {
    runId: payload.run_id,
    state: toRunLifecycleState(payload.status),
    rawStatus: payload.status,
    failureReported: payload.status.trim() === 'failed',
  }
}
