/**
 * Compact label/value rows with thin separators.
 *
 * A `null` value means the backend has not supplied that field. It is rendered
 * as an explicit "Not available" state instead of a placeholder, zero, or dash
 * that could be mistaken for a measured value.
 */
export interface DefinitionRow {
  id: string
  label: string
  value: string | null
  /** Optional context, e.g. unit or source of the value. */
  note?: string
}

interface DefinitionListProps {
  rows: DefinitionRow[]
  /** Describes where the values come from, e.g. "Backend not connected". */
  caption?: string
}

export function DefinitionList({ rows, caption }: DefinitionListProps) {
  return (
    <div>
      <dl style={{ margin: 0, display: 'flex', flexDirection: 'column' }}>
        {rows.map((row, index) => (
          <div
            key={row.id}
            style={{
              display: 'flex',
              alignItems: 'baseline',
              justifyContent: 'space-between',
              gap: 'var(--space-4)',
              padding: 'var(--space-2) 0',
              borderTop: index === 0 ? 'none' : '1px solid var(--border-secondary)',
            }}
          >
            <dt
              style={{
                margin: 0,
                fontSize: 'var(--text-sm)',
                color: 'var(--text-secondary)',
                fontFamily: 'var(--font-sans)',
                flexShrink: 0,
              }}
            >
              {row.label}
            </dt>
            <dd
              style={{
                margin: 0,
                fontSize: 'var(--text-sm)',
                fontFamily: 'var(--font-sans)',
                color: row.value === null ? 'var(--text-muted)' : 'var(--text-primary)',
                fontStyle: row.value === null ? 'italic' : 'normal',
                textAlign: 'right',
                overflowWrap: 'anywhere',
              }}
            >
              {row.value ?? 'Not available'}
              {row.value !== null && row.note ? (
                <span style={{ color: 'var(--text-muted)', fontStyle: 'normal' }}> {row.note}</span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>
      {caption ? (
        <p
          style={{
            margin: 'var(--space-3) 0 0 0',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          {caption}
        </p>
      ) : null}
    </div>
  )
}
