import { Link } from 'react-router-dom'
import { ApplicationShell } from '../components/layout/ApplicationShell'

export function NotFoundPage() {
  return (
    <ApplicationShell>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-3)',
          padding: 'var(--space-12) var(--space-4)',
          alignItems: 'center',
          textAlign: 'center',
        }}
      >
        <span
          style={{
            fontSize: 'var(--text-xs)',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          Not found
        </span>
        <h1
          style={{
            margin: 0,
            fontSize: 'var(--text-2xl)',
            fontWeight: 600,
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          This page does not exist
        </h1>
        <p
          style={{
            margin: 0,
            maxWidth: '48ch',
            fontSize: 'var(--text-base)',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          The address may be mistyped, or the destination has not been implemented. No
          experiment state was changed.
        </p>
        <Link
          to="/"
          style={{
            marginTop: 'var(--space-2)',
            padding: '8px 16px',
            background: 'var(--text-primary)',
            color: 'var(--bg-primary)',
            textDecoration: 'none',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--text-base)',
            fontFamily: 'var(--font-sans)',
            fontWeight: 500,
          }}
        >
          Back to overview
        </Link>
      </div>
    </ApplicationShell>
  )
}
