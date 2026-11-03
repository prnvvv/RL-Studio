/** Pure helpers for Compare mode (two sessions on the same environment and seed). */
import { formatInt, formatNumber, formatPercent } from './format'
import { MAX_LOGS, type StudioState } from './studioStore'
import type { BattleSide, LogEntry, Progress, SessionStatus } from './studioTypes'

/** When the two sides differ, the more "alive" state wins so the toolbar reflects what can still be controlled. */
const STATUS_PRIORITY: SessionStatus[] = [
  'failed',
  'stopping',
  'running',
  'paused',
  'initialized',
  'stopped',
  'completed',
]

export function combineStatus(
  a: SessionStatus | null,
  b: SessionStatus | null,
): SessionStatus | null {
  if (a === null) return b
  if (b === null) return a
  return STATUS_PRIORITY.find((status) => status === a || status === b) ?? a
}

/**
 * Who has the higher moving-average reward right now. This is the same rule the
 * backend uses; it is a snapshot, not a significance test, and is null until
 * both sides have finished an episode.
 */
export function leaderOf(a: Progress | null, b: Progress | null): BattleSide | null {
  const avgA = a?.current_reward_avg
  const avgB = b?.current_reward_avg
  if (typeof avgA !== 'number' || typeof avgB !== 'number' || avgA === avgB) return null
  return avgA > avgB ? 'a' : 'b'
}

export interface ComparisonRow {
  label: string
  a: string
  b: string
}

export function comparisonRows(a: Progress | null, b: Progress | null): ComparisonRow[] {
  const row = (label: string, pick: (p: Progress) => string): ComparisonRow => ({
    label,
    a: a ? pick(a) : '—',
    b: b ? pick(b) : '—',
  })
  return [
    row('Timestep', (p) => formatInt(p.timestep)),
    row('Episodes', (p) => formatInt(p.episodes)),
    row('Moving avg reward', (p) => formatNumber(p.current_reward_avg)),
    row('Reward / step', (p) => formatNumber(p.reward_per_step ?? null, 3)),
    row('Best reward', (p) => formatNumber(p.best_reward)),
    row('Success rate', (p) => formatPercent(p.success_rate)),
    row('Steps / sec', (p) => formatInt(p.steps_per_second)),
  ]
}

/** One console feed for both sides, each line prefixed with its side. Newest last, bounded. */
export function mergeLogs(a: LogEntry[], b: LogEntry[]): LogEntry[] {
  const tag = (side: string, entries: LogEntry[]) =>
    entries.map((entry) => ({ ...entry, message: `[${side}] ${entry.message}` }))
  const merged = [...tag('A', a), ...tag('B', b)].sort(
    (x, y) => x.timestamp.localeCompare(y.timestamp) || x.seq - y.seq,
  )
  return merged.length > MAX_LOGS ? merged.slice(merged.length - MAX_LOGS) : merged
}

/** A single `StudioState` for the shared chrome (toolbar, status, logs); side A supplies the rest. */
export function combineState(a: StudioState, b: StudioState, name: string | null): StudioState {
  return {
    ...a,
    name,
    status: combineStatus(a.status, b.status),
    pendingCommand: a.pendingCommand ?? b.pendingCommand,
    error: a.error ?? b.error,
    logs: mergeLogs(a.logs, b.logs),
    connection:
      a.connection === 'live' && b.connection === 'live'
        ? 'live'
        : a.connection === 'live'
          ? b.connection
          : a.connection,
  }
}
