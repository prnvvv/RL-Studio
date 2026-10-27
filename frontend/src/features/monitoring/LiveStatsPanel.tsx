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
  const common = {
    width: '12px',
    height: '12px',
    fill: 'none',
    stroke: 'var(--icon-secondary)',
    strokeWidth: 1.4,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  }

  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" style={{ flexShrink: 0 }} {...common}>
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

interface LiveStatsPanelProps {
  rows: LiveStatRow[]
}

export function LiveStatsPanel({ rows }: LiveStatsPanelProps) {
  return (
    <dl style={{ margin: 0, display: 'flex', flexDirection: 'column' }}>
      {rows.map((row, index) => (
        <div
          key={row.id}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 'var(--space-3)',
            padding: 'var(--space-3) 0',
            borderTop: index === 0 ? 'none' : '1px solid var(--border-secondary)',
          }}
        >
          <dt
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              margin: 0,
              fontSize: 'var(--text-sm)',
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            <StatIcon kind={row.kind} />
            {row.label}
          </dt>
          <dd
            style={{
              margin: 0,
              fontSize: 'var(--text-sm)',
              fontFamily: row.value === null ? 'var(--font-sans)' : 'var(--font-mono)',
              fontStyle: row.value === null ? 'italic' : 'normal',
              fontVariantNumeric: 'tabular-nums',
              color: row.value === null ? 'var(--text-muted)' : 'var(--text-primary)',
              textAlign: 'right',
            }}
          >
            {row.value === null ? (
              'Not available'
            ) : (
              <>
                {row.value}
                {row.unit ? <span style={{ color: 'var(--text-muted)' }}> {row.unit}</span> : null}
              </>
            )}
          </dd>
        </div>
      ))}
    </dl>
  )
}
