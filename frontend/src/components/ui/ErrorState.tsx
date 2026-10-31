import { ReactNode } from 'react'

interface ErrorStateProps {
  title: string
  /** Non-sensitive, user-safe failure message (from the service contract). */
  description: string
  /**
   * Retry affordance. Only pass a retry when repeating the request is safe —
   * never for destructive or consequential operations (§10.4, §15.3).
   */
  action?: ReactNode
}

/**
 * Request-failed state: the call was made and did not succeed. This is
 * distinct from `EmptyState` (successful request, nothing recorded) and from
 * `UnavailableState` (capability or data provider not available).
 *
 * Error states are announced with role="alert" since they usually follow an
 * explicit user action, and they never imply anything about the backend
 * operation's outcome beyond "no confirmed result".
 */
export function ErrorState({ title, description, action }: ErrorStateProps) {
  return (
    <div
      role="alert"
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
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '28px',
          height: '28px',
          border: '1px dashed var(--border-primary)',
          borderRadius: '50%',
          color: 'var(--text-secondary)',
          fontSize: 'var(--text-md)',
          fontWeight: 600,
        }}
      >
        !
      </span>
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
