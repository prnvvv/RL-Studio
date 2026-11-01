/**
 * Pending-state placeholder rendered by panels while a service request is in
 * flight (frontend/AGENTS.md §20.1).
 *
 * Deliberately a static, low-contrast bar group rather than an animated
 * shimmer: it stays honest in both themes, needs no motion accommodations, and
 * carries an accessible status label so screen-reader users know data is
 * loading rather than missing.
 */

interface LoadingSkeletonProps {
  /** Number of placeholder bars to render. Default 3. */
  rows?: number
}

export function LoadingSkeleton({ rows = 3 }: LoadingSkeletonProps) {
  return (
    <div
      role="status"
      aria-label="Loading data"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3)',
        padding: 'var(--space-4) 0',
      }}
    >
      {Array.from({ length: rows }, (_, index) => (
        <span
          key={index}
          aria-hidden="true"
          style={{
            height: '12px',
            width: index === rows - 1 ? '60%' : '100%',
            background: 'var(--bg-selected)',
            border: '1px solid var(--border-secondary)',
            borderRadius: 'var(--radius-sm)',
            display: 'block',
          }}
        />
      ))}
    </div>
  )
}
