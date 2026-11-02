import { describe, expect, it } from 'vitest'
import type { LiveEventPayload } from '../../schemas/events'
import { liveEventsToTimeline, liveEventToTimelineEvent } from './eventPresentation'

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

describe('liveEventToTimelineEvent', () => {
  it('uses the recorded event type as the title', () => {
    expect(liveEventToTimelineEvent(event()).title).toBe('reward_observed')
  })

  it('keeps a recorded timestamp and passes a null through unchanged', () => {
    expect(liveEventToTimelineEvent(event()).timestamp).toBe('2026-10-25T12:00:00Z')
    expect(liveEventToTimelineEvent(event({ timestamp: null })).timestamp).toBeNull()
  })

  it('does not guess a category from the event type', () => {
    // A name that looks like a recovery event must still be unclassified until
    // the mapping is agreed (TODO T-1004).
    const presented = liveEventToTimelineEvent(event({ event_type: 'recovery_completed' }))

    expect(presented.category).toBe('unknown')
  })

  it('composes detail text only from recorded fields', () => {
    expect(liveEventToTimelineEvent(event()).detail).toBe(
      'Episode episode_1 · Timestep 10 · Recorded reward 25 · Run run_1',
    )
  })

  it('omits missing fields instead of presenting them as zero', () => {
    const presented = liveEventToTimelineEvent(
      event({ episode_id: null, timestep: null, actual_reward: null }),
    )

    expect(presented.detail).toBe('Run run_1')
    expect(presented.detail).not.toMatch(/0/)
  })

  it('renders a recorded zero reward as a real value', () => {
    const presented = liveEventToTimelineEvent(event({ actual_reward: 0 }))

    expect(presented.detail).toContain('Recorded reward 0')
  })

  it('claims no source component the stream did not send', () => {
    expect(liveEventToTimelineEvent(event()).source).toBeUndefined()
  })

  it('keeps the event id so duplicates can be traced', () => {
    expect(liveEventToTimelineEvent(event({ event_id: 'evt_9' })).id).toBe('evt_9')
  })
})

describe('liveEventsToTimeline', () => {
  it('maps every event and preserves the supplied order', () => {
    const presented = liveEventsToTimeline([
      event({ event_id: 'evt_b', timestamp: '2026-10-25T12:01:00Z' }),
      event({ event_id: 'evt_a', timestamp: '2026-10-25T12:00:00Z' }),
    ])

    expect(presented.map((item) => item.id)).toEqual(['evt_b', 'evt_a'])
  })

  it('returns an empty list for an empty stream', () => {
    expect(liveEventsToTimeline([])).toEqual([])
  })
})
