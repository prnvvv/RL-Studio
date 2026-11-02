/**
 * Live event presentation — derived, deterministic.
 *
 * Maps the provisional event wire shape (`schemas/events.ts`) onto the
 * timeline's display model. Rules enforced:
 *
 * - The title is the recorded `event_type` verbatim. The mapping from backend
 *   event types onto the documented observation/verification/diagnosis/
 *   recovery/evaluation categories is not agreed (TODO T-1004), so every event
 *   is presented as unclassified rather than guessed into a category.
 * - Detail text is composed only from fields the stream recorded. A missing
 *   field is omitted from the sentence instead of being shown as a zero.
 * - No source component is claimed: the stream does not send one.
 */
import type { LiveEventPayload } from '../../schemas/events'
import type { TimelineEvent } from './EventTimeline'

/** Detail sentence parts that were actually recorded for the event. */
function recordedDetails(event: LiveEventPayload): string[] {
  const parts: string[] = []
  if (event.episode_id !== null) parts.push(`Episode ${event.episode_id}`)
  if (event.timestep !== null) parts.push(`Timestep ${event.timestep}`)
  if (event.actual_reward !== null) parts.push(`Recorded reward ${String(event.actual_reward)}`)
  if (event.run_id.trim() !== '') parts.push(`Run ${event.run_id}`)
  return parts
}

export function liveEventToTimelineEvent(event: LiveEventPayload): TimelineEvent {
  const detail = recordedDetails(event).join(' · ')

  return {
    id: event.event_id,
    timestamp: event.timestamp,
    category: 'unknown',
    title: event.event_type,
    ...(detail === '' ? {} : { detail }),
  }
}

export function liveEventsToTimeline(events: LiveEventPayload[]): TimelineEvent[] {
  return events.map(liveEventToTimelineEvent)
}
