import { ReactNode, useId, useState } from 'react'

interface ExpandableSectionProps {
  title: string
  /** Always-visible one-line summary of what the section contains. */
  summary?: string
  children: ReactNode
  /** Collapsed by default; open only when the content is essential on load. */
  defaultOpen?: boolean
}

/**
 * Keyboard-operable disclosure. The trigger is a real button, so Space/Enter,
 * focus order and `aria-expanded` come from the platform rather than custom
 * key handling.
 */
export function ExpandableSection({
  title,
  summary,
  children,
  defaultOpen = false,
}: ExpandableSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  const panelId = useId()
  const triggerId = useId()

  return (
    <section
      style={{
        borderTop: '1px solid var(--border-secondary)',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <h3 style={{ margin: 0 }}>
        <button
          type="button"
          id={triggerId}
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            width: '100%',
            padding: 'var(--space-3) 0',
            background: 'transparent',
            border: 'none',
            color: 'var(--text-primary)',
            textAlign: 'left',
            cursor: 'pointer',
            fontSize: 'var(--text-base)',
            fontWeight: 500,
            fontFamily: 'var(--font-sans)',
          }}
        >
          <span
            aria-hidden="true"
            style={{
              display: 'inline-flex',
              width: '12px',
              justifyContent: 'center',
              color: 'var(--text-muted)',
              fontSize: 'var(--text-xs)',
              transform: open ? 'rotate(90deg)' : 'none',
            }}
          >
            ▶
          </span>
          <span>{title}</span>
          <span
            style={{
              marginLeft: 'auto',
              fontSize: 'var(--text-xs)',
              color: 'var(--text-muted)',
              fontWeight: 400,
            }}
          >
            {open ? 'Collapse' : 'Expand'}
          </span>
        </button>
      </h3>
      {summary && !open ? (
        <p
          style={{
            margin: '0 0 var(--space-3) var(--space-5)',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-muted)',
          }}
        >
          {summary}
        </p>
      ) : null}
      <div
        id={panelId}
        role="region"
        aria-labelledby={triggerId}
        hidden={!open}
        style={{ padding: open ? '0 0 var(--space-4) var(--space-5)' : 0 }}
      >
        {open ? children : null}
      </div>
    </section>
  )
}
