import { ReactNode } from 'react'

interface PanelProps {
  title: string
  description?: string
  actions?: ReactNode
  children: ReactNode
  footer?: ReactNode
}

export function Panel({ title, description, actions, children, footer }: PanelProps) {
  return (
    <section
      style={{
        background: 'var(--bg-panel)',
        border: '1px solid var(--border-primary)',
        borderRadius: 'var(--radius-lg)',
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
      }}
      aria-label={title}
    >
      <header
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 'var(--space-4)',
          padding: 'var(--space-4)',
          borderBottom: '1px solid var(--border-secondary)',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
          <h2
            style={{
              margin: 0,
              fontSize: 'var(--text-md)',
              fontWeight: 600,
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            {title}
          </h2>
          {description && (
            <p
              style={{
                margin: 0,
                fontSize: 'var(--text-sm)',
                color: 'var(--text-secondary)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              {description}
            </p>
          )}
        </div>
        {actions && <div style={{ flexShrink: 0 }}>{actions}</div>}
      </header>
      <div style={{ padding: 'var(--space-4)', flex: 1, minWidth: 0 }}>{children}</div>
      {footer && (
        <footer
          style={{
            padding: 'var(--space-3) var(--space-4)',
            borderTop: '1px solid var(--border-secondary)',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          {footer}
        </footer>
      )}
    </section>
  )
}
