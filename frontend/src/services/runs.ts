/**
 * Runs service — PROVISIONAL Person 2 operational endpoints.
 *
 * Binds the mounted-but-undocumented `runs.router`
 * (`backend/api/routers/runs.py`, registered with `include_in_schema=False`):
 *
 * - `GET  /api/v1/runs/{run_id}/status` -> { run_id, status, error? }
 * - `POST /api/v1/runs/{run_id}/stop`   -> { run_id, status: "stop_requested", idempotent }
 * - `POST /api/v1/runs/start`           -> { run_id, status: "queued" }
 *
 * Behavior rules mirrored from the backend and root `AGENTS.md`:
 * - Status is reported as the backend states it; unrecognised values are not
 *   coerced into a lifecycle state (`schemas/runs.ts`).
 * - `stop` is idempotent server-side, so a repeated request is safe. The UI
 *   still prevents duplicate submissions while a request is in flight.
 * - `start` has no idempotency key or dedupe: a retried start can queue a
 *   second worker task for the same id. Callers must not retry automatically.
 * - A timeout or network failure never implies a terminal run state.
 * - The worker's failure text is not surfaced; a failed status only reports
 *   that a failure was recorded.
 */
import type {
  RunLifecycle,
  RunLifecycleState,
  RunStartRequest,
  RunStatusPayload,
} from '../schemas/runs'
import {
  parseRunStartPayload,
  parseRunStatusPayload,
  parseRunStopPayload,
  toRunLifecycle,
} from '../schemas/runs'
import type { ServiceResult } from './types'
import { serviceError } from './types'
import { api } from './client'

const UNEXPECTED_MESSAGE = 'The service returned an unexpected response.'

export function runStatusPath(runId: string): string {
  return `/api/v1/runs/${encodeURIComponent(runId)}/status`
}

export function runStopPath(runId: string): string {
  return `/api/v1/runs/${encodeURIComponent(runId)}/stop`
}

export function runStartPath(): string {
  return '/api/v1/runs/start'
}

/**
 * The stop endpoint acknowledges a request; it does not prove the run stopped.
 * The lifecycle shown after a stop must come from the status endpoint.
 */
export interface RunStopAcknowledgement {
  runId: string
  /** State derived from the acknowledgement (`stop_requested` when reported). */
  state: RunLifecycleState
  rawStatus: string
  /** True when the backend reported the request as idempotent. */
  idempotent: boolean
}

export interface RunService {
  getRunStatus(runId: string, signal?: AbortSignal): Promise<ServiceResult<RunLifecycle>>
  startRun(request: RunStartRequest): Promise<ServiceResult<RunLifecycle>>
  stopRun(runId: string): Promise<ServiceResult<RunStopAcknowledgement>>
}

function unexpected<T>(): ServiceResult<T> {
  return serviceError('unexpected', UNEXPECTED_MESSAGE)
}

/** Real-mode adapter against the operational run endpoints. */
const realAdapter: RunService = {
  async getRunStatus(runId, signal) {
    const result = await api.get<RunStatusPayload>(runStatusPath(runId), { signal })
    if (result.state === 'error') return result
    const payload = parseRunStatusPayload(result.data)
    if (payload === null) return unexpected<RunLifecycle>()
    return { state: 'ok', data: toRunLifecycle(payload) }
  },

  async startRun(request) {
    const result = await api.post<unknown>(runStartPath(), { jsonBody: { run_id: request.run_id } })
    if (result.state === 'error') return result
    const payload = parseRunStartPayload(result.data)
    if (payload === null) return unexpected<RunLifecycle>()
    return { state: 'ok', data: toRunLifecycle(payload) }
  },

  async stopRun(runId) {
    const result = await api.post<unknown>(runStopPath(runId))
    if (result.state === 'error') return result
    const payload = parseRunStopPayload(result.data)
    if (payload === null) return unexpected<RunStopAcknowledgement>()
    return {
      state: 'ok',
      data: {
        runId: payload.run_id,
        state: toRunLifecycle({ run_id: payload.run_id, status: payload.status }).state,
        rawStatus: payload.status,
        idempotent: payload.idempotent === true,
      },
    }
  },
}

/** Select the runs adapter. Currently only the real adapter exists. */
export function createRunService(): RunService {
  return realAdapter
}
