import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { LiveEventPayload } from '../schemas/events'
import type {
  LiveEventStream,
  LiveEventStreamOptions,
  LiveTransportState,
} from '../services/events'
import { useLiveEvents } from './useLiveEvents'

function event(overrides: Partial<LiveEventPayload> = {}): LiveEventPayload {
  return {
    event_id: 'evt_1',
    event_type: 'reward_observed',
    run_id: 'run_1',
    episode_id: 'episode_1',
    timestep: 10,
    actual_reward: 25,
    timestamp: '2026-10-25T12:00:00Z',
    ...overrides,
  }
}

interface Recorder {
  options: LiveEventStreamOptions[]
  closed: number
  retries: number
}

function harness(throwOnCreate = false) {
  const recorder: Recorder = { options: [], closed: 0, retries: 0 }

  function createStream(options: LiveEventStreamOptions): LiveEventStream {
    if (throwOnCreate) throw new Error('unsupported protocol')
    recorder.options.push(options)
    return {
      close() {
        recorder.closed += 1
      },
      retry() {
        recorder.retries += 1
      },
    }
  }

  function emitState(state: LiveTransportState) {
    recorder.options[recorder.options.length - 1].onState(state)
  }

  function emitEvents(batch: LiveEventPayload[]) {
    recorder.options[recorder.options.length - 1].onEvents(batch)
  }

  return { recorder, createStream, emitState, emitEvents }
}

describe('useLiveEvents', () => {
  it('does not connect without a selected run and says so honestly', () => {
    const probe = harness()
    const { result } = renderHook(() => useLiveEvents(null, { createStream: probe.createStream }))

    expect(result.current.connection).toBe('not_configured')
    expect(result.current.events).toEqual([])
    expect(result.current.lastUpdated).toBeNull()
    expect(probe.recorder.options).toHaveLength(0)
  })

  it('reports transport state as it changes', () => {
    const probe = harness()
    const { result } = renderHook(() =>
      useLiveEvents('run_1', { createStream: probe.createStream }),
    )

    expect(result.current.connection).toBe('connecting')
    act(() => probe.emitState('connected'))
    expect(result.current.connection).toBe('connected')
    act(() => probe.emitState('reconnecting'))
    expect(result.current.connection).toBe('reconnecting')
    act(() => probe.emitState('disconnected'))
    expect(result.current.connection).toBe('disconnected')
  })

  it('merges batches, suppresses replayed duplicates and records the update time', () => {
    const probe = harness()
    const { result } = renderHook(() =>
      useLiveEvents('run_1', { createStream: probe.createStream }),
    )

    act(() => probe.emitState('connected'))
    act(() => probe.emitEvents([event()]))
    expect(result.current.events).toHaveLength(1)
    expect(result.current.lastUpdated).not.toBeNull()

    // A reconnect replays the server's recent events; they must not duplicate.
    act(() =>
      probe.emitEvents([event(), event({ event_id: 'evt_2', timestamp: '2026-10-25T12:01:00Z' })]),
    )

    expect(result.current.events.map((item) => item.event_id)).toEqual(['evt_2', 'evt_1'])
  })

  it('discards the previous run’s events and closes its stream when the run changes', () => {
    const probe = harness()
    const initialProps: { runId: string | null } = { runId: 'run_1' }
    const { result, rerender } = renderHook(
      ({ runId }: { runId: string | null }) =>
        useLiveEvents(runId, { createStream: probe.createStream }),
      { initialProps },
    )

    act(() => probe.emitEvents([event()]))
    expect(result.current.events).toHaveLength(1)

    rerender({ runId: 'run_2' })

    expect(probe.recorder.closed).toBe(1)
    expect(result.current.events).toEqual([])
    expect(result.current.lastUpdated).toBeNull()
    expect(probe.recorder.options).toHaveLength(2)

    rerender({ runId: null })
    expect(result.current.connection).toBe('not_configured')
    expect(probe.recorder.closed).toBe(2)
  })

  it('closes the stream on unmount', () => {
    const probe = harness()
    const { unmount } = renderHook(() =>
      useLiveEvents('run_1', { createStream: probe.createStream }),
    )

    unmount()

    expect(probe.recorder.closed).toBe(1)
  })

  it('delegates an explicit retry to the transport', () => {
    const probe = harness()
    const { result } = renderHook(() =>
      useLiveEvents('run_1', { createStream: probe.createStream }),
    )

    act(() => result.current.retry())

    expect(probe.recorder.retries).toBe(1)
  })

  it('reports a transport that cannot start without pretending it connected', () => {
    const probe = harness(true)
    const { result } = renderHook(() =>
      useLiveEvents('run_1', { createStream: probe.createStream }),
    )

    expect(result.current.connection).toBe('disconnected')
    expect(result.current.transportError).toMatch(/could not be started/i)
    expect(result.current.events).toEqual([])
  })

  it('ignores late callbacks from a closed stream', () => {
    const probe = harness()
    const { result, rerender } = renderHook(
      ({ runId }: { runId: string | null }) =>
        useLiveEvents(runId, { createStream: probe.createStream }),
      { initialProps: { runId: 'run_1' } },
    )
    const firstOptions = probe.recorder.options[0]

    rerender({ runId: 'run_2' })
    act(() => {
      firstOptions.onState('connected')
      firstOptions.onEvents([event({ event_id: 'late' })])
    })

    expect(result.current.connection).toBe('connecting')
    expect(result.current.events).toEqual([])
  })
})
