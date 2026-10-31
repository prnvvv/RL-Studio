interface StaleDataNoticeProps {
  /** When the currently displayed data was recorded, if known. */
  asOf?: string
  /** What may be affected by the staleness, e.g. "training stats". */
  subject?: string
}

/**
 * Small inline notice marking that displayed values may be out of date
 * (`frontend/AGENTS.md` §11.3, §20.4).
 *
 * It never asserts what the backend is doing now — a lost connection does not
 * imply that training, recovery, or evaluation stopped, so the wording stays
 * strictly about the freshness of displayed values.
 */
export function StaleDataNotice({ asOf, subject }: StaleDataNoticeProps) {
  const noun = subject ? `${subject} may be out of date` : 'Displayed data may be out of date'
  return (
    <span
      role="status"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        padding: '2px 8px',
        border: '1px dashed var(--border-primary)',
        borderRadius: '999px',
        fontSize: 'var(--text-xs)',
        color: 'var(--text-secondary)',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <span
        aria-hidden="true"
        style={{ display: 'inline-flex', border: '1px solid var(--border-primary)', width: '8px', height: '8px', borderRadius: '50%' }}
      />
      {noun}
      {asOf ? <span style={{ color: 'var(--text-muted)' }}>as of {asOf}</span> : null}
    </span>
  )
}
