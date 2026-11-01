import { formatUtcDate, formatUtcTime } from '../../utils/datetime'
import type { EvidenceReference } from '../../schemas/verification'

interface EvidenceEventListProps {
  evidence: EvidenceReference[]
  /** Present when the parent can navigate to an evidence detail view. */
  onOpenEvidence?: (evidenceId: string) => void
}

/** Render an ISO timestamp as `YYYY-MM-DD HH:MM:SSZ`, or "not recorded". */
function displayTimestamp(timestamp: string | null): string {
  if (!timestamp) return 'Time not recorded'
  const date = formatUtcDate(timestamp)
  const time = formatUtcTime(timestamp)
  return date && time ? `${date} ${time}` : 'Time not recorded'
}

/**
 * Chronological list of the evidence references backing a verification or
 * investigation. References are stable identifiers — displayed as text (or
 * navigation buttons when the parent wires a detail view), never rendered as
 * fabricated event bodies.
 */
export function EvidenceEventList({ evidence, onOpenEvidence }: EvidenceEventListProps) {
  const ordered = [...evidence].sort((a, b) => {
    const at = a.timestamp ? Date.parse(a.timestamp) : Number.NaN
    const bt = b.timestamp ? Date.parse(b.timestamp) : Number.NaN
    if (Number.isNaN(at) && Number.isNaN(bt)) return a.id.localeCompare(b.id)
    if (Number.isNaN(at)) return 1
    if (Number.isNaN(bt)) return -1
    return at - bt
  })

  return (
    <ol
      style={{
        listStyle: 'none',
        margin: 0,
        padding: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {ordered.map((ref) => (
        <li
          key={ref.id}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-1)',
            padding: 'var(--space-2) 0',
            borderTop: '1px solid var(--border-secondary)',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              flexWrap: 'wrap',
            }}
          >
            {onOpenEvidence ? (
              <button
                type="button"
                onClick={() => onOpenEvidence(ref.id)}
                style={{
                  padding: '2px 8px',
                  background: 'transparent',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius-sm)',
                  color: 'var(--text-primary)',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                }}
              >
                {ref.id}
              </button>
            ) : (
              <code
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-primary)',
                }}
              >
                {ref.id}
              </code>
            )}
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
              Source: {ref.source}
            </span>
          </div>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            {displayTimestamp(ref.timestamp)}
            {ref.run_identifier ? ` · Run: ${ref.run_identifier}` : ''}
            {ref.environment_identifier ? ` · Environment: ${ref.environment_identifier}` : ''}
            {ref.location ? ` · Location: ${ref.location}` : ''}
          </span>
        </li>
      ))}
    </ol>
  )
}
