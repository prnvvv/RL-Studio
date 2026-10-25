import { ApplicationShell } from '../components/layout/ApplicationShell'

export function TrainingPage() {
  return (
    <ApplicationShell>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 600, margin: 0, color: 'var(--text-primary)', fontFamily: 'var(--font-sans)' }}>
              Training Dashboard
            </h1>
            <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-secondary)', margin: '4px 0 0 0', fontFamily: 'var(--font-sans)' }}>
              Configure and monitor reinforcement learning training runs
            </p>
          </div>
          <button
            style={{
              padding: '8px 16px',
              background: 'var(--text-primary)',
              color: 'var(--bg-primary)',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              fontSize: 'var(--text-base)',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            New Training Run
          </button>
        </div>
      </div>
    </ApplicationShell>
  )
}
