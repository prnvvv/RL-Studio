import { useCallback, useEffect, useRef, useState } from 'react'
import type { RunLifecycle } from '../schemas/runs'
import { isTerminalRunState } from '../schemas/runs'
import type { RunService } from '../services/runs'
import type { ServiceQueryState } from './useServiceQuery'

/** Status polling cadence while a run is non-terminal. */
export const RUN_STATUS_POLL_INTERVAL_MS = 5_000

export interface RunStatusPolling {
  state: ServiceQueryState<RunLifecycle>
  /** ISO time the last successful status response was received, or null. */
  lastUpdated: string | null
  /**
   * True when the latest poll failed but earlier status data is retained.
   * A poll failure never changes the last known lifecycle state.
   */
  stale: boolean
  /** Re-poll immediately (resets the retained-failure marker on success). */
  reload: () => void
}

/**
 * Poll `GET /runs/{run_id}/status` until the run reaches a canonical terminal
 * state.
 *
 * - Status is backend-authoritative: a failed poll keeps the last recorded
 *   lifecycle and marks it stale rather than inferring a failure or stop.
 * - Polling stops at canonical terminal states; unknown or unrecognised states
 *   keep polling because they cannot be assumed final.
 * - A different `runId` discards the previous run's data instead of showing it
 *   under the new identifier; components should still key on the id.
 */
export function useRunStatus(
  runId: string,
  service: RunService,
  options: { intervalMs?: number } = {},
): RunStatusPolling {
  const intervalMs = options.intervalMs ?? RUN_STATUS_POLL_INTERVAL_MS
  const [state, setState] = useState<ServiceQueryState<RunLifecycle>>({ state: 'loading' })
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [stale, setStale] = useState(false)
  const [reloadNonce, setReloadNonce] = useState(0)

  const lastDataRef = useRef<RunLifecycle | null>(null)
  const activeRunIdRef = useRef(runId)

  useEffect(() => {
    if (activeRunIdRef.current !== runId) {
      activeRunIdRef.current = runId
      lastDataRef.current = null
      setState({ state: 'loading' })
      setLastUpdated(null)
      setStale(false)
    }

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null
    let controller: AbortController | null = null

    async function poll() {
      if (cancelled) return

      controller = new AbortController()
      const result = await service.getRunStatus(runId, controller.signal)
      if (cancelled) return

      if (result.state === 'ok') {
        lastDataRef.current = result.data
        setState(result)
        setLastUpdated(new Date().toISOString())
        setStale(false)

        if (isTerminalRunState(result.data.state)) return
      } else {
        setState({ ...result, data: lastDataRef.current })
        setStale(lastDataRef.current !== null)
      }

      timer = setTimeout(() => {
        timer = null
        void poll()
      }, intervalMs)
    }

    void poll()

    return () => {
      cancelled = true
      controller?.abort()
      if (timer !== null) clearTimeout(timer)
    }
  }, [runId, service, intervalMs, reloadNonce])

  const reload = useCallback(() => {
    setReloadNonce((nonce) => nonce + 1)
  }, [])

  return { state, lastUpdated, stale, reload }
}
