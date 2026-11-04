export type StatKind = 'episode' | 'steps' | 'reward' | 'success' | 'time'

export interface LiveStatRow {
  id: string
  label: string
  kind: StatKind
  /** Formatted value, or `null` when the backend has not supplied one. */
  value: string | null
  /** Unit or measurement qualifier, e.g. "%" or "steps/s". */
  unit?: string
}

function StatIcon({ kind }: { kind: StatKind }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="mon-stat__icon">
      {kind === 'episode' && <circle cx="8" cy="8" r="5" />}
      {kind === 'steps' && (
        <>
          <path d="M3 6l5-3 5 3" />
          <path d="M3 11l5-3 5 3" />
        </>
      )}
      {kind === 'reward' && (
        <path d="M8 2.5l1.7 3.6 3.8.5-2.8 2.7.7 3.8L8 11.3l-3.4 1.8.7-3.8L2.5 6.6l3.8-.5z" />
      )}
      {kind === 'success' && <path d="M3 8.5l3.2 3L13 4.5" />}
      {kind === 'time' && (
        <>
          <circle cx="8" cy="8" r="5.5" />
          <path d="M8 4.8V8l2.4 1.6" />
        </>
      )}
    </svg>
  )
}

/** A fixed, decorative waveform. It is not derived from data and encodes nothing. */
function DecorativeWave() {
  return (
    <svg viewBox="0 0 56 16" aria-hidden="true" className="mon-stat__wave">
      <path d="M1 9c4-7 7-7 11 0s7 7 11 0 7-7 11 0 7 7 11 0" />
    </svg>
  )
}

interface LiveStatsPanelProps {
  rows: LiveStatRow[]
}

export function LiveStatsPanel({ rows }: LiveStatsPanelProps) {
  return (
    <dl className="mon-stats">
      {rows.map((row) => (
        <div key={row.id} className="mon-stat">
          <dt className="mon-stat__label">
            <StatIcon kind={row.kind} />
            {row.label}
          </dt>
          <DecorativeWave />
          <dd className="mon-stat__value">
            {row.value === null ? (
              <span className="mon-badge">Not available</span>
            ) : (
              <>
                {row.value}
                {row.unit ? <span className="mon-stat__unit"> {row.unit}</span> : null}
              </>
            )}
          </dd>
        </div>
      ))}
    </dl>
  )
}
