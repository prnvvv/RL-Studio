import { Link } from 'react-router-dom'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import { MetricCard } from '../components/ui/MetricCard'
import { WarehouseIllustration } from '../components/illustrations/WarehouseIllustration'

// No run data has been loaded, so no metric is claimed. A dash is rendered
// rather than a zero, because zero would look like a measured value.
const summaryMetrics = [
  { id: 'active-runs', label: 'Active Training Runs', value: '—' },
  { id: 'recovery-rate', label: 'Recovery Rate', value: '—' },
  { id: 'total-steps', label: 'Total Steps', value: '—' },
]

export function HomePage() {
  return (
    <ApplicationShell>
      <div className="page-stack">
        <div className="hero-layout">
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
                letterSpacing: '-0.01em',
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
                maxWidth: '52ch',
              }}
            >
              A platform for resilient warehouse operations. Configure, train, monitor, diagnose,
              and recover reinforcement-learning agents.
            </p>
            <div className="action-row" style={{ marginTop: 'var(--space-2)' }}>
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
              <Link
                to="/login"
                style={{
                  padding: '8px 16px',
                  background: 'var(--bg-panel)',
                  color: 'var(--text-primary)',
                  textDecoration: 'none',
                  border: '1px dashed var(--border-primary)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 'var(--text-base)',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                Login
              </Link>
              <Link
                to="/training#intent"
                style={{
                  padding: '8px 16px',
                  background: 'var(--bg-panel)',
                  color: 'var(--text-secondary)',
                  textDecoration: 'none',
                  border: '1px dashed var(--border-primary)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 'var(--text-base)',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                Describe intended behaviour
              </Link>
            </div>
          </div>

          <figure
            style={{
              margin: 0,
              padding: 'var(--space-4)',
              background: 'var(--bg-panel)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-lg)',
            }}
          >
            <WarehouseIllustration />
            <figcaption
              style={{
                marginTop: 'var(--space-2)',
                fontSize: 'var(--text-xs)',
                color: 'var(--text-muted)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Illustration preview — not a running simulation.
            </figcaption>
          </figure>
        </div>

        <div className="metric-row">
          {summaryMetrics.map((metric) => (
            <MetricCard key={metric.id} label={metric.label} value={metric.value} />
          ))}
        </div>
      </div>
    </ApplicationShell>
  )
}
