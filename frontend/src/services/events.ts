/**
 * Live execution events — WebSocket transport.
 *
 * The only event transport Person 2 currently exposes is
 * `WS /api/v1/events/{run_id}` (`backend/api/routers/ws_events.py`). There is
 * no HTTP snapshot/history endpoint, and the SSE handler is not bound because
 * its generator yields objects rather than string frames (malformed SSE).
 *
 * Consequences handled here:
 * - The server replays its most recent events on every connection. That replay
 *   is the only "snapshot" available, so it is delivered through the same
 *   `onEvents` callback and duplicates are suppressed downstream by
 *   `mergeLiveEvents`.
 * - Reconnects use bounded exponential backoff with jitter; after the attempt
 *   budget is exhausted the stream reports `disconnected` and waits for an
 *   explicit `retry()` rather than looping forever.
 * - Frames that are not the documented shape are dropped, never coerced.
 * - `close()` is silent: a deliberate teardown must not imply that the run
 *   stopped or failed.
 */
import { decodeLiveEventFrame, type LiveEventPayload } from '../schemas/events'
import { withProjectScope } from './projectScope'

export type LiveTransportState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected'

/** Minimal WebSocket surface so tests can inject a deterministic socket. */
export interface SocketLike {
  onopen: (() => void) | null
  onmessage: ((event: { data: unknown }) => void) | null
  onerror: ((event: unknown) => void) | null
  onclose: ((event: unknown) => void) | null
  close(): void
}

export interface LiveEventStreamOptions {
  runId: string
  onState: (state: LiveTransportState) => void
  onEvents: (events: LiveEventPayload[]) => void
  /** Injectable socket factory; defaults to the browser WebSocket. */
  createSocket?: (url: string) => SocketLike
  /** API base URL; defaults to `VITE_API_BASE_URL`. */
  baseUrl?: string
  /** Origin used when the API base URL is empty; defaults to the page origin. */
  origin?: string
  /** Jitter source in [0, 1); injectable for deterministic tests. */
  random?: () => number
  maxAttempts?: number
  baseDelayMs?: number
  maxDelayMs?: number
}

export interface LiveEventStream {
  /** Stop reconnecting and close the socket. No state is emitted afterwards. */
  close(): void
  /** Manual retry, e.g. after the bounded attempt budget was exhausted. */
  retry(): void
}

export const DEFAULT_MAX_ATTEMPTS = 5
export const DEFAULT_BASE_DELAY_MS = 1_000
export const DEFAULT_MAX_DELAY_MS = 15_000

/**
 * Compose the WebSocket URL for a run's event stream from the HTTP API base.
 * `http`/`https` become `ws`/`wss`; an empty base means the page origin.
 */
export function buildEventStreamUrl(baseUrl: string, runId: string, origin: string): string {
  const normalizedBase = baseUrl.trim().replace(/\/+$/, '')
  const source = normalizedBase === '' ? origin : normalizedBase

  const url = new URL(source)
  if (url.protocol === 'http:') url.protocol = 'ws:'
  else if (url.protocol === 'https:') url.protocol = 'wss:'
  else if (url.protocol !== 'ws:' && url.protocol !== 'wss:') {
    throw new Error(`Unsupported API base URL protocol: ${url.protocol}`)
  }

  const prefix = url.pathname.replace(/\/+$/, '')
  url.pathname = `${prefix}/api/v1/events/${encodeURIComponent(runId)}`
  url.search = ''
  url.hash = ''
  return url.toString()
}

function defaultCreateSocket(url: string): SocketLike {
  return new WebSocket(url) as unknown as SocketLike
}

function resolveBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL?.trim() ?? ''
}

function resolveOrigin(): string {
  return typeof window === 'undefined' ? 'http://localhost' : window.location.origin
}

export function createLiveEventStream(options: LiveEventStreamOptions): LiveEventStream {
  const {
    runId,
    onState,
    onEvents,
    createSocket = defaultCreateSocket,
    baseUrl = resolveBaseUrl(),
    origin = resolveOrigin(),
    random = Math.random,
    maxAttempts = DEFAULT_MAX_ATTEMPTS,
    baseDelayMs = DEFAULT_BASE_DELAY_MS,
    maxDelayMs = DEFAULT_MAX_DELAY_MS,
  } = options

  const url = withProjectScope(buildEventStreamUrl(baseUrl, runId, origin))

  let closed = false
  let generation = 0
  let attempt = 0
  let socket: SocketLike | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  function clearTimer() {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  function teardownSocket() {
    if (socket !== null) {
      const current = socket
      socket = null
      current.onopen = null
      current.onmessage = null
      current.onerror = null
      current.onclose = null
      try {
        current.close()
      } catch {
        // A socket that cannot be closed cleanly is already unusable.
      }
    }
  }

  function scheduleReconnect() {
    if (closed) return
    attempt += 1
    if (attempt > maxAttempts) {
      onState('disconnected')
      return
    }

    const backoff = Math.min(maxDelayMs, baseDelayMs * 2 ** (attempt - 1))
    const jittered = Math.round(backoff * (0.5 + random() * 0.5))
    onState('reconnecting')
    timer = setTimeout(() => {
      timer = null
      open()
    }, jittered)
  }

  function handleDrop(currentGeneration: number) {
    if (closed || currentGeneration !== generation) return
    // Invalidate this generation so onerror/onclose for the same socket only
    // schedule one reconnect.
    generation += 1
    teardownSocket()
    scheduleReconnect()
  }

  function open() {
    if (closed) return

    const currentGeneration = generation
    let current: SocketLike
    try {
      current = createSocket(url)
    } catch {
      scheduleReconnect()
      return
    }
    socket = current

    current.onopen = () => {
      if (closed || currentGeneration !== generation) return
      attempt = 0
      onState('connected')
    }
    current.onmessage = (event) => {
      if (closed || currentGeneration !== generation) return
      const parsed = decodeLiveEventFrame(event.data)
      if (parsed !== null) onEvents([parsed])
    }
    current.onerror = () => {
      handleDrop(currentGeneration)
    }
    current.onclose = () => {
      handleDrop(currentGeneration)
    }
  }

  onState('connecting')
  open()

  return {
    close() {
      closed = true
      generation += 1
      clearTimer()
      teardownSocket()
    },
    retry() {
      if (closed) return
      clearTimer()
      teardownSocket()
      attempt = 0
      onState('connecting')
      open()
    },
  }
}
