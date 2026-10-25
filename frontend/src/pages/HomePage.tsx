import { Link } from 'react-router-dom'
import { ApplicationShell } from '../components/layout/ApplicationShell'

export function HomePage() {
  return (
    <ApplicationShell>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-8)', alignItems: 'center' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <span
              style={{
                fontSize: 'var(--text-xs)',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                color: 'var(--text-muted)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Welcome
            </span>
            <h1
              style={{
                fontSize: 'var(--text-3xl)',
                fontWeight: 600,
                margin: 0,
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Train. Monitor. Recover.
            </h1>
            <p
              style={{
                fontSize: 'var(--text-md)',
                color: 'var(--text-secondary)',
                margin: 0,
                fontFamily: 'var(--font-sans)',
                lineHeight: 1.6,
              }}
            >
              A platform for resilient warehouse operations. Configure, train, monitor, diagnose, and recover reinforcement-learning agents.
            </p>
            <div style={{ display: 'flex', gap: 'var(--space-3)', marginTop: 'var(--space-2)' }}>
              <Link
                to="/training"
                style={{
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
                Start Training
              </Link>
              <Link
                to="/environments"
                style={{
                  padding: '8px 16px',
                  background: 'var(--bg-panel)',
                  color: 'var(--text-primary)',
                  textDecoration: 'none',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 'var(--text-base)',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                View Environments
              </Link>
            </div>
          </div>
          <div
            style={{
              height: '320px',
              background: 'var(--bg-panel)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-lg)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--text-muted)',
              fontSize: 'var(--text-sm)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            Warehouse Simulation (Preview)
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-4)' }}>
          {[
            { label: 'Active Training Runs', value: '0' },
            { label: 'Recovery Rate', value: '—' },
            { label: 'Total Steps', value: '0' },
          ].map((card) => (
            <div
              key={card.label}
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
                {card.label}
              </span>
              <span
                style={{
                  fontSize: 'var(--text-2xl)',
                  fontWeight: 600,
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                {card.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </ApplicationShell>
  )
}
