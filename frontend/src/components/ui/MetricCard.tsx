interface MetricCardProps {
  label: string
  value: string
  trend?: string
}

export function MetricCard({ label, value, trend }: MetricCardProps) {
  return (
    <div
      style={{
        padding: 'var(--space-4)',
        background: 'var(--bg-panel)',
        border: '1px solid var(--border-primary)',
        borderRadius: 'var(--radius-lg)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
      }}
    >
      <span
        style={{
          fontSize: 'var(--text-sm)',
          color: 'var(--text-secondary)',
          fontFamily: 'var(--font-sans)',
        }}
      >
        {label}
      </span>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <span
          style={{
            fontSize: 'var(--text-2xl)',
            fontWeight: 600,
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          {value}
        </span>
        {trend && (
          <span
            style={{
              fontSize: 'var(--text-sm)',
              color: 'var(--text-muted)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            {trend}
          </span>
        )}
      </div>
    </div>
  )
}
