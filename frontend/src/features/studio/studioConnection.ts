/**
 * WebSocket connection to one session's live stream.
 *
 * Protocol (see `backend/api/routers/studio.py`):
 * - the first message is always a full `snapshot`;
 * - then ordered `StudioEvent`s (strictly increasing `seq`) and coalesced `frame`s.
 *
 * On any drop the client reconnects with bounded exponential backoff. Because
 * every connection starts with a fresh snapshot, a gap can never leave the
 * view stale or silently inconsistent.
 */
import type { FrameMessage, SessionSnapshot, StudioEvent } from './studioTypes'
import type { StudioStore } from './studioStore'

export interface ConnectionOptions {
  url: (after: number) => string
  /** Injectable for tests. */
  createSocket?: (url: string) => WebSocket
  minDelayMs?: number
  maxDelayMs?: number
  /** Latency probe interval; 0 disables pings. */
  pingIntervalMs?: number
  /** Injectable clock for tests. */
  now?: () => number
}

type StreamMessage =
  | { type: 'snapshot'; payload: SessionSnapshot }
  | { type: 'pong'; t: number }
  | FrameMessage
  | StudioEvent

function parse(raw: unknown): StreamMessage | null {
  if (typeof raw !== 'string') return null
  try {
    const value = JSON.parse(raw) as unknown
    if (typeof value !== 'object' || value === null) return null
    const type = (value as { type?: unknown }).type
    return typeof type === 'string' ? (value as StreamMessage) : null
  } catch {
    return null
  }
}

/** Open the stream (the session is identified by `options.url`). Returns a disposer that closes it and stops reconnecting. */
export function connectSession(store: StudioStore, options: ConnectionOptions): () => void {
  const minDelay = options.minDelayMs ?? 500
  const maxDelay = options.maxDelayMs ?? 8000
  const create = options.createSocket ?? ((url: string) => new WebSocket(url))
  const pingInterval = options.pingIntervalMs ?? 2000
  const now = options.now ?? (() => performance.now())
  let pinger: ReturnType<typeof setInterval> | null = null
  const stopPinging = () => {
    if (pinger !== null) clearInterval(pinger)
    pinger = null
  }

  let socket: WebSocket | null = null
  let disposed = false
  let attempt = 0
  let timer: ReturnType<typeof setTimeout> | null = null

  const open = () => {
    if (disposed) return
    store.setConnection(attempt === 0 ? 'connecting' : 'reconnecting')
    const ws = create(options.url(store.getState().lastSeq))
    socket = ws

    ws.onopen = () => {
      if (pingInterval <= 0) return
      const ping = () => {
        if (ws.readyState === 1) ws.send(JSON.stringify({ type: 'ping', t: now() }))
      }
      ping()
      stopPinging()
      pinger = setInterval(ping, pingInterval)
    }

    ws.onmessage = (event: MessageEvent) => {
      const message = parse(event.data)
      if (message === null) return
      attempt = 0
      if (message.type === 'pong') {
        store.recordRtt(now() - (message as { t: number }).t)
      } else if (message.type === 'snapshot') {
        store.applySnapshot((message as { payload: SessionSnapshot }).payload)
        store.setConnection('live')
      } else if (message.type === 'frame') {
        store.applyFrame((message as FrameMessage).payload)
      } else {
        store.applyEvent(message as StudioEvent)
      }
    }

    ws.onclose = (closeEvent: CloseEvent) => {
      stopPinging()
      if (disposed) return
      // 4404: the backend does not know this session; retrying cannot help.
      if (closeEvent.code === 4404) {
        store.setConnection('closed')
        return
      }
      store.setConnection('reconnecting')
      const delay = Math.min(maxDelay, minDelay * 2 ** attempt)
      attempt += 1
      timer = setTimeout(open, delay)
    }
    ws.onerror = () => {
      // `onclose` always follows and owns the retry; nothing else to do here.
    }
  }

  open()

  return () => {
    disposed = true
    stopPinging()
    if (timer !== null) clearTimeout(timer)
    if (socket !== null) {
      socket.onclose = null
      socket.onmessage = null
      socket.close()
    }
    store.setConnection('closed')
  }
}
