import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  buildEventStreamUrl,
  createLiveEventStream,
  DEFAULT_MAX_ATTEMPTS,
  type LiveTransportState,
  type SocketLike,
} from './events'

class FakeSocket implements SocketLike {
  static instances: FakeSocket[] = []

  onopen: (() => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null
  onerror: ((event: unknown) => void) | null = null
  onclose: ((event: unknown) => void) | null = null
  closed = false

  constructor(public readonly url: string) {
    FakeSocket.instances.push(this)
  }

  close() {
    this.closed = true
  }

  emitOpen() {
    this.onopen?.()
  }

  emitMessage(data: unknown) {
    this.onmessage?.({ data })
  }

  emitError() {
    this.onerror?.({})
  }

  emitClose() {
    this.onclose?.({})
  }
}

function lastSocket(): FakeSocket {
  return FakeSocket.instances[FakeSocket.instances.length - 1]
}

const frame = {
  event_id: 'evt_1',
  event_type: 'reward_observed',
  run_id: 'run_1',
  episode_id: 'episode_1',
  timestep: 10,
  actual_reward: 25,
  timestamp: '2026-10-25T12:00:00Z',
}

function setup(overrides: Partial<Parameters<typeof createLiveEventStream>[0]> = {}) {
  const states: LiveTransportState[] = []
  const batches: unknown[] = []
  const stream = createLiveEventStream({
    runId: 'run_1',
    baseUrl: 'http://localhost:8000',
    origin: 'http://localhost:5173',
    random: () => 1, // deterministic upper jitter bound
    createSocket: (url) => new FakeSocket(url),
    onState: (state) => states.push(state),
    onEvents: (events) => batches.push(events),
    ...overrides,
  })
  return { stream, states, batches }
}

beforeEach(() => {
  FakeSocket.instances = []
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('buildEventStreamUrl', () => {
  it('maps the HTTP API base onto the event WebSocket path', () => {
    expect(buildEventStreamUrl('http://localhost:8000/', 'run 1', 'http://localhost:5173')).toBe(
      'ws://localhost:8000/api/v1/events/run%201',
    )
  })

  it('uses wss for an https API base', () => {
    expect(buildEventStreamUrl('https://api.example.com', 'run_1', 'https://app.example.com')).toBe(
      'wss://api.example.com/api/v1/events/run_1',
    )
  })

  it('falls back to the page origin when the API base is empty', () => {
    expect(buildEventStreamUrl('', 'run_1', 'https://app.example.com')).toBe(
      'wss://app.example.com/api/v1/events/run_1',
    )
  })

  it('rejects an unsupported base URL protocol', () => {
    expect(() => buildEventStreamUrl('ftp://example.com', 'run_1', 'http://localhost')).toThrow(
      /Unsupported API base URL protocol/,
    )
  })
})

describe('createLiveEventStream', () => {
  it('reports connecting then connected and forwards valid frames', () => {
    const { states, batches } = setup()

    expect(states).toEqual(['connecting'])
    lastSocket().emitOpen()
    expect(states).toEqual(['connecting', 'connected'])

    lastSocket().emitMessage(JSON.stringify(frame))
    expect(batches).toEqual([[frame]])
  })

  it('drops malformed frames instead of rendering guessed data', () => {
    const { batches } = setup()
    lastSocket().emitOpen()

    lastSocket().emitMessage('{not json')
    lastSocket().emitMessage(JSON.stringify({ event_type: 'reward_observed' }))
    lastSocket().emitMessage(null)

    expect(batches).toEqual([])
  })

  it('reconnects once per dropped socket, with backoff, and resumes on open', () => {
    const { states } = setup()
    lastSocket().emitOpen()

    // Browsers may fire both error and close for one failure.
    lastSocket().emitError()
    lastSocket().emitClose()

    expect(states).toEqual(['connecting', 'connected', 'reconnecting'])
    expect(FakeSocket.instances).toHaveLength(1)

    // First backoff is baseDelayMs * 2^0, scaled by jitter (random = 1 -> 1.0x).
    vi.advanceTimersByTime(999)
    expect(FakeSocket.instances).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(FakeSocket.instances).toHaveLength(2)

    lastSocket().emitOpen()
    expect(states[states.length - 1]).toBe('connected')

    // The server replays recent events on reconnect; the transport forwards
    // them and the events layer suppresses duplicates by id.
    lastSocket().emitMessage(JSON.stringify(frame))
  })

  it('backs off exponentially and stops after the bounded attempt budget', () => {
    const { states } = setup()

    for (let attempt = 1; attempt <= DEFAULT_MAX_ATTEMPTS; attempt += 1) {
      lastSocket().emitError()
      expect(states[states.length - 1]).toBe('reconnecting')
      vi.advanceTimersByTime(DEFAULT_MAX_ATTEMPTS * 30_000)
    }

    lastSocket().emitError()
    expect(states[states.length - 1]).toBe('disconnected')
    expect(FakeSocket.instances).toHaveLength(DEFAULT_MAX_ATTEMPTS + 1)

    // No further automatic attempt is made.
    vi.advanceTimersByTime(10 * 60_000)
    expect(FakeSocket.instances).toHaveLength(DEFAULT_MAX_ATTEMPTS + 1)
  })

  it('retries explicitly after the budget is exhausted', () => {
    const { stream, states } = setup()

    for (let attempt = 0; attempt <= DEFAULT_MAX_ATTEMPTS; attempt += 1) {
      lastSocket().emitError()
      vi.advanceTimersByTime(DEFAULT_MAX_ATTEMPTS * 30_000)
    }
    expect(states[states.length - 1]).toBe('disconnected')

    stream.retry()
    expect(states[states.length - 1]).toBe('connecting')
    expect(FakeSocket.instances.length).toBe(DEFAULT_MAX_ATTEMPTS + 2)
  })

  it('stays silent after close and never reconnects', () => {
    const { stream, states } = setup()
    lastSocket().emitOpen()

    stream.close()
    expect(lastSocket().closed).toBe(true)

    lastSocket().emitClose()
    vi.advanceTimersByTime(10 * 60_000)

    expect(states).toEqual(['connecting', 'connected'])
    expect(FakeSocket.instances).toHaveLength(1)
  })
})
