import { ReactNode } from 'react'

interface EmptyStateProps {
  title: string
  description: string
  /** Only pass an action when it performs a real, supported operation. */
  action?: ReactNode
}

/**
 * Empty state: the request succeeded and there is genuinely nothing recorded.
 * This is distinct from `UnavailableState` (capability/data not provided) and
 * from `ErrorState` (the request failed).
 */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div
      role="status"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--space-2)',
        padding: 'var(--space-10) var(--space-4)',
        textAlign: 'center',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: '26px',
          height: '26px',
          border: '1px solid var(--border-primary)',
          borderRadius: 'var(--radius-sm)',
        }}
      />
      <span style={{ fontSize: 'var(--text-base)', color: 'var(--text-primary)' }}>{title}</span>
      <span
        style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', maxWidth: '48ch' }}
      >
        {description}
      </span>
      {action ? <div style={{ marginTop: 'var(--space-2)' }}>{action}</div> : null}
    </div>
  )
}
