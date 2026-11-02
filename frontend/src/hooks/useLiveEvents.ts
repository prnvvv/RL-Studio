import { useCallback, useEffect, useRef, useState } from 'react'
import type { LiveEventPayload } from '../schemas/events'
import { mergeLiveEvents } from '../schemas/events'
import type { LiveConnectionState } from '../features/monitoring/LiveConnectionStatus'
import type { LiveEventStream, LiveEventStreamOptions } from '../services/events'
import { createLiveEventStream } from '../services/events'

export interface LiveEventsOptions {
  /**
   * Inject a transport factory (tests, or a future transport swap). Defaults to
   * the WebSocket stream in `services/events.ts`.
   */
  createStream?: (options: LiveEventStreamOptions) => LiveEventStream
}

export interface LiveEventsResult {
  /**
   * Transport state. `not_configured` means no run is selected and therefore
   * no connection was attempted — never a claim that training is idle.
   */
  connection: LiveConnectionState
  /** Bounded, de-duplicated events, most recent first. */
  events: LiveEventPayload[]
  /** ISO time the most recent batch arrived, or null when nothing has arrived. */
  lastUpdated: string | null
  /**
   * Set when the transport could not even be created (for example an
   * unsupported configured API base). The message is generic and safe to show.
   */
  transportError: string | null
  /** Re-open the stream after the bounded reconnect budget is exhausted. */
  retry: () => void
}

const TRANSPORT_ERROR_MESSAGE = 'The live-update connection could not be started.'

/**
 * Subscribe to a run's live event stream.
 *
 * - One connection per selected run; changing `runId` discards the previous
 *   run's events instead of showing them under the new identifier, and closes
 *   the old socket.
 * - Events are merged through `mergeLiveEvents`, so a reconnect replay does not
 *   duplicate history and the retained window stays bounded.
 * - The hook reports transport state only. It never infers that a run stopped,
 *   failed, or completed from a lost connection.
 * - Teardown is silent: unmounting is not an event about the run.
 */
export function useLiveEvents(
  runId: string | null,
  options: LiveEventsOptions = {},
): LiveEventsResult {
  const createStream = options.createStream ?? createLiveEventStream

  const [connection, setConnection] = useState<LiveConnectionState>(
    runId === null ? 'not_configured' : 'connecting',
  )
  const [events, setEvents] = useState<LiveEventPayload[]>([])
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [transportError, setTransportError] = useState<string | null>(null)
  const streamRef = useRef<LiveEventStream | null>(null)

  useEffect(() => {
    setEvents([])
    setLastUpdated(null)
    setTransportError(null)

    if (runId === null) {
      setConnection('not_configured')
      return
    }

    let disposed = false
    setConnection('connecting')

    let stream: LiveEventStream
    try {
      stream = createStream({
        runId,
        onState: (state) => {
          if (disposed) return
          setConnection(state)
        },
        onEvents: (batch) => {
          if (disposed) return
          setEvents((previous) => mergeLiveEvents(previous, batch))
          setLastUpdated(new Date().toISOString())
        },
      })
    } catch {
      setConnection('disconnected')
      setTransportError(TRANSPORT_ERROR_MESSAGE)
      return
    }

    streamRef.current = stream

    return () => {
      disposed = true
      streamRef.current = null
      stream.close()
    }
  }, [runId, createStream])

  const retry = useCallback(() => {
    streamRef.current?.retry()
  }, [])

  return { connection, events, lastUpdated, transportError, retry }
}
