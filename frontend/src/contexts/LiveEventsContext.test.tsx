import { act, render, renderHook, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { LiveEventPayload } from '../schemas/events'
import type {
  LiveEventStream,
  LiveEventStreamOptions,
  LiveTransportState,
} from '../services/events'
import { LiveEventsProvider, useLiveEventsContext } from './LiveEventsContext'

function event(overrides: Partial<LiveEventPayload> = {}): LiveEventPayload {
  return {
    event_id: 'evt_1',
    event_type: 'reward_observed',
    run_id: 'run_1',
    episode_id: null,
    timestep: null,
    actual_reward: null,
    timestamp: '2026-10-25T12:00:00Z',
    ...overrides,
  }
}

function harness() {
  const options: LiveEventStreamOptions[] = []
  let closed = 0
  const createStream = (streamOptions: LiveEventStreamOptions): LiveEventStream => {
    options.push(streamOptions)
    return {
      close() {
        closed += 1
      },
      retry() {},
    }
  }
  return {
    createStream,
    options,
    closedCount: () => closed,
  }
}

function Probe() {
  const live = useLiveEventsContext()
  return (
    <div>
      <span data-testid="state">{live.connection}</span>
      <span data-testid="count">{live.events.length}</span>
    </div>
  )
}

describe('LiveEventsProvider', () => {
  it('opens no connection without a run and reports not configured', () => {
    const probe = harness()
    render(
      <LiveEventsProvider runId={null} createStream={probe.createStream}>
        <Probe />
      </LiveEventsProvider>,
    )

    expect(probe.options).toHaveLength(0)
    expect(screen.getByTestId('state')).toHaveTextContent('not_configured')
  })

  it('shares one subscription between consumers', () => {
    const probe = harness()
    render(
      <LiveEventsProvider runId="run_1" createStream={probe.createStream}>
        <Probe />
        <Probe />
      </LiveEventsProvider>,
    )

    expect(probe.options).toHaveLength(1)
    expect(screen.getAllByTestId('state').map((node) => node.textContent)).toEqual([
      'connecting',
      'connecting',
    ])
  })

  it('reflects transport state and recorded events for every consumer', () => {
    const probe = harness()
    render(
      <LiveEventsProvider runId="run_1" createStream={probe.createStream}>
        <Probe />
        <Probe />
      </LiveEventsProvider>,
    )

    act(() => {
      probe.options[0].onState('connected')
      probe.options[0].onEvents([event()])
    })

    expect(screen.getAllByTestId('state').map((node) => node.textContent)).toEqual([
      'connected',
      'connected',
    ])
    expect(screen.getAllByTestId('count').map((node) => node.textContent)).toEqual(['1', '1'])
  })

  it('closes the subscription when the run scope is cleared', () => {
    const probe = harness()
    const { rerender } = render(
      <LiveEventsProvider runId="run_1" createStream={probe.createStream}>
        <Probe />
      </LiveEventsProvider>,
    )

    rerender(
      <LiveEventsProvider runId={null} createStream={probe.createStream}>
        <Probe />
      </LiveEventsProvider>,
    )

    expect(probe.closedCount()).toBe(1)
    expect(screen.getByTestId('state')).toHaveTextContent('not_configured')
  })

  it('throws a clear error when used outside the provider', () => {
    const consoleError = console.error
    console.error = () => {}
    try {
      expect(() => renderHook(() => useLiveEventsContext())).toThrow(
        /must be used within a LiveEventsProvider/i,
      )
    } finally {
      console.error = consoleError
    }
  })

  it('exposes the transport error instead of pretending a connection exists', () => {
    function FailingProbe() {
      const live = useLiveEventsContext()
      return (
        <div>
          <span data-testid="state">{live.connection}</span>
          <span data-testid="transport">{live.transportError ?? 'none'}</span>
        </div>
      )
    }
    const createStream = () => {
      throw new Error('unsupported protocol')
    }

    render(
      <LiveEventsProvider runId="run_1" createStream={createStream}>
        <FailingProbe />
      </LiveEventsProvider>,
    )

    expect(screen.getByTestId('state')).toHaveTextContent('disconnected')
    expect(screen.getByTestId('transport')).toHaveTextContent(/could not be started/i)
  })
})

// Keep the transport state type referenced so a future change to the union is
// a compile error here rather than a silent mismatch.
const states: LiveTransportState[] = ['connecting', 'connected', 'reconnecting', 'disconnected']
void states
