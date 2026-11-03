import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { connectSession } from './studioConnection'
import { StudioStore } from './studioStore'

class FakeSocket {
  readyState = 1
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  send(data: string) {
    this.sent.push(data)
  }
  close() {
    this.readyState = 3
  }
}

describe('connection latency probe', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  function open(clock: { t: number }) {
    const store = new StudioStore()
    const socket = new FakeSocket()
    const dispose = connectSession(store, {
      url: () => 'ws://test',
      createSocket: () => socket as unknown as WebSocket,
      pingIntervalMs: 1000,
      now: () => clock.t,
    })
    return { store, socket, dispose }
  }

  it('measures round-trip time from the echoed timestamp', () => {
    const clock = { t: 100 }
    const { store, socket, dispose } = open(clock)
    socket.onopen?.()
    expect(JSON.parse(socket.sent[0])).toEqual({ type: 'ping', t: 100 })
    clock.t = 112
    socket.onmessage?.({ data: JSON.stringify({ type: 'pong', t: 100 }) })
    expect(store.stream.rttMs).toBe(12)
    dispose()
  })

  it('keeps pinging on an interval and stops after dispose', () => {
    const clock = { t: 0 }
    const { socket, dispose } = open(clock)
    socket.onopen?.()
    vi.advanceTimersByTime(2500)
    expect(socket.sent).toHaveLength(3)
    dispose()
    vi.advanceTimersByTime(5000)
    expect(socket.sent).toHaveLength(3)
  })

  it('counts received simulation frames', () => {
    const { store, socket, dispose } = open({ t: 0 })
    socket.onmessage?.({
      data: JSON.stringify({
        type: 'frame',
        frame_seq: 1,
        session_id: 's',
        payload: { timestep: 1 },
      }),
    })
    expect(store.stream.frames).toBe(1)
    dispose()
  })
})
