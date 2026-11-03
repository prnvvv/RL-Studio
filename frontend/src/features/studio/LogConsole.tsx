import { useEffect, useMemo, useRef, useState } from 'react'
import type { LogCategory, LogEntry, LogLevel } from './studioTypes'

const LEVELS: LogLevel[] = ['INFO', 'WARNING', 'ERROR']
const CATEGORIES: LogCategory[] = ['TRAINING', 'ENVIRONMENT', 'AGENT', 'FAULT', 'RECOVERY', 'CHECKPOINT']
const VISIBLE_ROWS = 500

export function filterLogs(
  logs: LogEntry[],
  filters: { level: LogLevel | 'ALL'; category: LogCategory | 'ALL'; query: string },
): LogEntry[] {
  const query = filters.query.trim().toLowerCase()
  return logs.filter((entry) => {
    if (filters.level !== 'ALL' && entry.level !== filters.level) return false
    if (filters.category !== 'ALL' && entry.category !== filters.category) return false
    if (!query) return true
    return (
      entry.message.toLowerCase().includes(query) ||
      JSON.stringify(entry.meta).toLowerCase().includes(query)
    )
  })
}

function timeOf(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '--:--:--' : d.toLocaleTimeString('en-GB', { hour12: false })
}

/** Live event console: filter, search, pause scrolling, expand structured metadata. */
export function LogConsole({ logs }: { logs: LogEntry[] }) {
  const [level, setLevel] = useState<LogLevel | 'ALL'>('ALL')
  const [category, setCategory] = useState<LogCategory | 'ALL'>('ALL')
  const [query, setQuery] = useState('')
  const [follow, setFollow] = useState(true)
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(new Set())
  const listRef = useRef<HTMLDivElement>(null)

  const visible = useMemo(
    () => filterLogs(logs, { level, category, query }).slice(-VISIBLE_ROWS),
    [logs, level, category, query],
  )

  useEffect(() => {
    const node = listRef.current
    if (follow && node) node.scrollTop = node.scrollHeight
  }, [visible, follow])

  const toggle = (seq: number) =>
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(seq)) next.delete(seq)
      else next.add(seq)
      return next
    })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="log-tools">
        <input type="search" placeholder="Search logs" aria-label="Search logs" value={query} onChange={(e) => setQuery(e.target.value)} />
        <select aria-label="Filter by level" value={level} onChange={(e) => setLevel(e.target.value as LogLevel | 'ALL')}>
          <option value="ALL">All levels</option>
          {LEVELS.map((l) => (
            <option key={l} value={l}>{l}</option>
          ))}
        </select>
        <select aria-label="Filter by category" value={category} onChange={(e) => setCategory(e.target.value as LogCategory | 'ALL')}>
          <option value="ALL">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <button type="button" className="btn btn--ghost" aria-pressed={follow} onClick={() => setFollow((f) => !f)}>
          {follow ? 'Pause scrolling' : 'Resume scrolling'}
        </button>
        <span style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>
          {visible.length} of {logs.length}
        </span>
      </div>
      <div ref={listRef} className="log-list" role="log" aria-live="off" aria-label="Event log" style={{ flex: 1 }}>
        {visible.length === 0 ? (
          <div className="empty">{logs.length === 0 ? 'No events yet.' : 'No events match the filters.'}</div>
        ) : (
          visible.map((entry) => (
            <div key={entry.seq} className="log-row" data-level={entry.level}>
              <span className="log-row__time">{timeOf(entry.timestamp)}</span>
              <span className="log-row__cat">{entry.level}</span>
              <span className="log-row__cat">{entry.category}</span>
              <button type="button" aria-expanded={expanded.has(entry.seq)} onClick={() => toggle(entry.seq)}>
                {entry.message}
              </button>
              {expanded.has(entry.seq) && (
                <pre className="log-detail">
                  {JSON.stringify(
                    { session_id: entry.session_id, run_id: entry.run_id, episode_id: entry.episode_id, seq: entry.seq, timestamp: entry.timestamp, ...entry.meta },
                    null,
                    2,
                  )}
                </pre>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
