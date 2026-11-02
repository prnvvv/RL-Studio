/**
 * Live execution events — PROVISIONAL wire contract.
 *
 * Person 2 currently exposes execution events over a WebSocket
 * (`backend/api/routers/ws_events.py`) fed by `backend/events/service.py`:
 *
 *     { event_id, event_type, run_id, episode_id, timestep, actual_reward, timestamp }
 *
 * This is deliberately NOT `ExecutionEventEnvelope` from `schemas/shared.ts`.
 * The canonical envelope requires `schema_version`, `sequence`, and
 * `source_component`, none of which the stream sends; two parallel event
 * schemas are a known Person 2 gap. Until the transport and envelope are
 * agreed (T-009 / T-601), the frontend:
 *
 * - accepts only the fields the stream actually sends;
 * - drops a frame that is not that shape instead of inventing the missing
 *   envelope fields;
 * - keeps event-type semantics unclassified (T-1004) rather than guessing a
 *   category from the name.
 *
 * No HTTP event-history endpoint exists. The only reads are the WebSocket
 * stream and the SSE handler, whose frames are currently not valid SSE (it
 * yields objects rather than strings), so SSE is not bound.
 */
/** Bounded retained window; long-running streams must not grow without limit. */
export const MAX_LIVE_EVENTS = 200

export interface LiveEventPayload {
  event_id: string
  event_type: string
  run_id: string
  episode_id: string | null
  timestep: number | null
  actual_reward: number | null
  timestamp: string | null
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim() !== ''
}

function optionalString(value: unknown): string | null | undefined {
  if (value === undefined || value === null) return null
  return typeof value === 'string' ? value : undefined
}

function optionalNumber(value: unknown): number | null | undefined {
  if (value === undefined || value === null) return null
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

/**
 * Validate one decoded frame. Returns `null` for anything that is not the
 * documented stream shape; callers must ignore such frames rather than render
 * guessed event data.
 */
export function parseLiveEvent(value: unknown): LiveEventPayload | null {
  if (typeof value !== 'object' || value === null) return null
  const record = value as Record<string, unknown>

  if (!isNonEmptyString(record.event_id)) return null
  if (!isNonEmptyString(record.event_type)) return null
  if (!isNonEmptyString(record.run_id)) return null

  const episodeId = optionalString(record.episode_id)
  const timestep = optionalNumber(record.timestep)
  const actualReward = optionalNumber(record.actual_reward)
  const timestamp = optionalString(record.timestamp)

  if (episodeId === undefined || timestep === undefined) return null
  if (actualReward === undefined || timestamp === undefined) return null

  return {
    event_id: record.event_id,
    event_type: record.event_type,
    run_id: record.run_id,
    episode_id: episodeId,
    timestep,
    actual_reward: actualReward,
    timestamp,
  }
}

/**
 * Decode a WebSocket frame. Frames are expected to be JSON text; a malformed
 * frame yields `null` rather than throwing.
 */
export function decodeLiveEventFrame(data: unknown): LiveEventPayload | null {
  if (typeof data !== 'string') return parseLiveEvent(data)
  try {
    return parseLiveEvent(JSON.parse(data))
  } catch {
    return null
  }
}

/**
 * Merge incoming events into the bounded live window.
 *
 * - Duplicate event ids are suppressed (reconnects replay the server's recent
 *   events, so duplicates are expected and must not multiply history).
 * - Ordering uses the recorded timestamp, newest first. Timestamps are the only
 *   ordering field the stream supplies (there is no sequence number); events
 *   with no recorded timestamp sort last and keep their arrival order.
 * - The window is bounded so a long-running stream cannot grow without limit.
 */
export function mergeLiveEvents(
  existing: LiveEventPayload[],
  incoming: LiveEventPayload[],
): LiveEventPayload[] {
  const byId = new Map<string, LiveEventPayload>()
  for (const event of existing) byId.set(event.event_id, event)
  for (const event of incoming) byId.set(event.event_id, event)

  const merged = [...byId.values()]
  const timed: LiveEventPayload[] = []
  const untimed: LiveEventPayload[] = []
  for (const event of merged) {
    if (event.timestamp !== null && !Number.isNaN(Date.parse(event.timestamp))) timed.push(event)
    else untimed.push(event)
  }

  timed.sort((a, b) => Date.parse(b.timestamp as string) - Date.parse(a.timestamp as string))
  return [...timed, ...untimed].slice(0, MAX_LIVE_EVENTS)
}
