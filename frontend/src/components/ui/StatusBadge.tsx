import { ReactNode } from 'react'

/**
 * Visual tone. Deliberately named for emphasis rather than meaning, so no
 * backend status can be mapped to a colour-coded "success"/"danger" without a
 * deliberate decision. Colour is never the only signal: every badge shows text.
 */
export type StatusTone = 'neutral' | 'strong' | 'quiet'

export type StatusGlyph = 'none' | 'check' | 'dot' | 'cross' | 'query'

interface StatusBadgeProps {
  label: string
  tone?: StatusTone
  glyph?: StatusGlyph
  /** Optional qualifier such as "estimate" or "advisory". */
  note?: ReactNode
}

const toneStyles: Record<
  StatusTone,
  { border: string; background: string; color: string; borderStyle: string }
> = {
  neutral: {
    border: '1px solid var(--border-primary)',
    background: 'transparent',
    color: 'var(--text-primary)',
    borderStyle: 'solid',
  },
  strong: {
    border: '1px solid var(--text-primary)',
    background: 'var(--text-primary)',
    color: 'var(--bg-primary)',
    borderStyle: 'solid',
  },
  quiet: {
    border: '1px dashed var(--border-primary)',
    background: 'transparent',
    color: 'var(--text-muted)',
    borderStyle: 'dashed',
  },
}

function Glyph({ glyph, color }: { glyph: StatusGlyph; color: string }) {
  if (glyph === 'none') return null

  const common = {
    width: '9px',
    height: '9px',
    fill: 'none',
    stroke: color,
    strokeWidth: 1.6,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  }

  return (
    <svg viewBox="0 0 12 12" style={{ flexShrink: 0 }} {...common}>
      {glyph === 'check' && <path d="M2 6.5l2.6 2.5L10 3.5" />}
      {glyph === 'dot' && <circle cx="6" cy="6" r="2.6" fill={color} stroke="none" />}
      {glyph === 'cross' && (
        <>
          <path d="M3 3l6 6" />
          <path d="M9 3l-6 6" />
        </>
      )}
      {glyph === 'query' && (
        <>
          <path d="M4.4 4.2a1.7 1.7 0 113 1.1c-.5.5-1.4.8-1.4 1.8" />
          <circle cx="6" cy="9.4" r="0.7" fill={color} stroke="none" />
        </>
      )}
    </svg>
  )
}

export function StatusBadge({ label, tone = 'neutral', glyph = 'none', note }: StatusBadgeProps) {
  const styles = toneStyles[tone]

  return (
    <span
      data-tone={tone}
      data-glyph={glyph}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        padding: '2px 8px',
        border: styles.border,
        borderStyle: styles.borderStyle,
        borderRadius: '999px',
        background: styles.background,
        color: styles.color,
        fontSize: 'var(--text-xs)',
        fontFamily: 'var(--font-sans)',
        lineHeight: 1.6,
        whiteSpace: 'nowrap',
      }}
    >
      <Glyph glyph={glyph} color={styles.color} />
      {label}
      {note ? <span style={{ opacity: 0.72, fontStyle: 'italic' }}>{note}</span> : null}
    </span>
  )
}
