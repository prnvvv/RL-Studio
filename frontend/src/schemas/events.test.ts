import { describe, expect, it } from 'vitest'
import {
  MAX_LIVE_EVENTS,
  decodeLiveEventFrame,
  mergeLiveEvents,
  parseLiveEvent,
  type LiveEventPayload,
} from './events'

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

describe('parseLiveEvent', () => {
  it('accepts the documented stream frame', () => {
    expect(parseLiveEvent(event())).toEqual(event())
  })

  it('accepts null optional fields as recorded nulls', () => {
    expect(
      parseLiveEvent({
        event_id: 'evt_1',
        event_type: 'training_started',
        run_id: 'run_1',
        episode_id: null,
        timestep: null,
        actual_reward: null,
        timestamp: null,
      }),
    ).toEqual({
      event_id: 'evt_1',
      event_type: 'training_started',
      run_id: 'run_1',
      episode_id: null,
      timestep: null,
      actual_reward: null,
      timestamp: null,
    })
  })

  it('rejects frames missing required identifiers', () => {
    expect(parseLiveEvent(null)).toBeNull()
    expect(parseLiveEvent({})).toBeNull()
    expect(parseLiveEvent({ ...event(), event_id: '' })).toBeNull()
    expect(parseLiveEvent({ ...event(), event_type: '' })).toBeNull()
    expect(parseLiveEvent({ ...event(), run_id: undefined })).toBeNull()
  })

  it('rejects frames whose optional fields have the wrong type', () => {
    expect(parseLiveEvent({ ...event(), timestep: '10' })).toBeNull()
    expect(parseLiveEvent({ ...event(), actual_reward: Number.NaN })).toBeNull()
    expect(parseLiveEvent({ ...event(), episode_id: 7 })).toBeNull()
    expect(parseLiveEvent({ ...event(), timestamp: 123 })).toBeNull()
  })
})

describe('decodeLiveEventFrame', () => {
  it('decodes a JSON text frame', () => {
    expect(decodeLiveEventFrame(JSON.stringify(event()))).toEqual(event())
  })

  it('returns null for malformed JSON instead of throwing', () => {
    expect(decodeLiveEventFrame('{not json')).toBeNull()
    expect(decodeLiveEventFrame('')).toBeNull()
  })

  it('accepts an already-decoded object frame', () => {
    expect(decodeLiveEventFrame(event())).toEqual(event())
  })
})

describe('mergeLiveEvents', () => {
  it('suppresses duplicate event ids across reconnects', () => {
    const merged = mergeLiveEvents(
      [event()],
      [event(), event({ event_id: 'evt_2', timestamp: '2026-10-25T12:01:00Z' })],
    )

    expect(merged.map((item) => item.event_id)).toEqual(['evt_2', 'evt_1'])
  })

  it('orders by recorded timestamp, newest first, without inventing times', () => {
    const merged = mergeLiveEvents(
      [event({ event_id: 'evt_old', timestamp: '2026-10-25T12:00:00Z' })],
      [
        event({ event_id: 'evt_new', timestamp: '2026-10-25T12:04:00Z' }),
        event({ event_id: 'evt_mid', timestamp: '2026-10-25T12:02:00Z' }),
      ],
    )

    expect(merged.map((item) => item.event_id)).toEqual(['evt_new', 'evt_mid', 'evt_old'])
  })

  it('keeps events with no recorded timestamp and sorts them last', () => {
    const merged = mergeLiveEvents(
      [],
      [
        event({ event_id: 'evt_untimed', timestamp: null }),
        event({ event_id: 'evt_timed', timestamp: '2026-10-25T12:00:00Z' }),
      ],
    )

    expect(merged.map((item) => item.event_id)).toEqual(['evt_timed', 'evt_untimed'])
  })

  it('bounds the retained window', () => {
    const incoming = Array.from({ length: MAX_LIVE_EVENTS + 10 }, (_, index) =>
      event({
        event_id: `evt_${index}`,
        timestamp: new Date(Date.UTC(2026, 9, 25, 12, 0, index)).toISOString(),
      }),
    )

    const merged = mergeLiveEvents([], incoming)

    expect(merged).toHaveLength(MAX_LIVE_EVENTS)
    expect(merged[0].event_id).toBe(`evt_${MAX_LIVE_EVENTS + 9}`)
  })
})
