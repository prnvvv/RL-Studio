import { Link } from 'react-router-dom'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import { Panel } from '../components/ui/Panel'
import { EmptyState } from '../components/ui/EmptyState'
import { UnavailableState } from '../components/ui/UnavailableState'
import { LineChart } from '../components/charts/LineChart'
import { EventTimeline, TimelineEvent } from '../features/monitoring/EventTimeline'
import { LiveStatsPanel, LiveStatRow } from '../features/monitoring/LiveStatsPanel'
import {
  LiveConnectionStatus,
  LiveConnectionState,
} from '../features/monitoring/LiveConnectionStatus'

// No event feed, run, or metrics snapshot is connected. These are empty
// collections, not placeholder content: the page renders "nothing recorded"
// and "not available" rather than inventing training history.
const recordedEvents: TimelineEvent[] = []

// Transport choice is not yet agreed (TODO T-601 / T-1007), so the honest state
// is "not configured" rather than a simulated "Live" indicator.
const connectionState: LiveConnectionState = 'not_configured'

const liveStats: LiveStatRow[] = [
  { id: 'episode', label: 'Episode', kind: 'episode', value: null },
  { id: 'total-steps', label: 'Total Steps', kind: 'steps', value: null },
  { id: 'avg-reward', label: 'Average Reward', kind: 'reward', value: null },
  { id: 'success-rate', label: 'Success Rate', kind: 'success', value: null },
  { id: 'training-time', label: 'Training Time', kind: 'time', value: null },
]

export function MonitoringPage() {
  return (
    <ApplicationShell>
      <div className="page-stack">
        <div className="page-header">
          <div>
            <h1
              style={{
                fontSize: 'var(--text-2xl)',
                fontWeight: 600,
                margin: 0,
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Monitoring
            </h1>
            <p
              style={{
                fontSize: 'var(--text-base)',
                color: 'var(--text-secondary)',
                margin: '4px 0 0 0',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Observe training behaviour and recorded execution events
            </p>
          </div>
        </div>

        <LiveConnectionStatus state={connectionState} lastUpdated={null} />

        <div className="monitor-layout">
          <Panel
            title="Recent Events"
            description="Training metrics context. Events appear only when the backend recorded them."
            actions={
              <button
                type="button"
                disabled
                title="No generated event history is available to open"
                style={{
                  padding: '5px 10px',
                  background: 'transparent',
                  color: 'var(--text-muted)',
                  border: '1px solid var(--border-primary)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: 'var(--text-xs)',
                  fontFamily: 'var(--font-sans)',
                  cursor: 'not-allowed',
                }}
              >
                View All
              </button>
            }
          >
            {recordedEvents.length === 0 ? (
              <EmptyState
                title="No events recorded for this scope"
                description="Training starts, fault injections, detected violations, diagnosis updates, recovery actions, and evaluation results appear here once a run records them."
              />
            ) : (
              <EventTimeline events={recordedEvents} totalCount={undefined} />
            )}
          </Panel>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <Panel
              title="Live Stats"
              description="Training metrics, not held-out evaluation metrics."
            >
              <LiveStatsPanel rows={liveStats} />
              <p
                style={{
                  margin: 'var(--space-3) 0 0 0',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-muted)',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                Values are populated from a run snapshot. Nothing is interpolated or estimated.
              </p>
            </Panel>

            <Panel title="Related views">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                <Link
                  to="/training"
                  style={{
                    fontSize: 'var(--text-sm)',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-sans)',
                  }}
                >
                  Training dashboard
                </Link>
                <Link
                  to="/diagnosis-recovery"
                  style={{
                    fontSize: 'var(--text-sm)',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-sans)',
                  }}
                >
                  Diagnosis &amp; Recovery
                </Link>
                <Link
                  to="/reports"
                  style={{
                    fontSize: 'var(--text-sm)',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-sans)',
                  }}
                >
                  Training history
                </Link>
              </div>
            </Panel>
          </div>
        </div>

        <Panel
          title="Comparison Charts"
          description="Reward trend against healthy, faulty, and recovered baselines. Secondary to the areas above."
        >
          <LineChart
            title="Reward versus training steps by run"
            series={[]}
            xLabel="Training steps"
            yLabel="Episode reward"
          />
          <div style={{ marginTop: 'var(--space-3)' }}>
            <UnavailableState
              title="No comparison series available"
              description="Baseline, faulty, and recovered series are drawn only from recorded evaluation and training metrics. No run has been loaded."
              owner="Person 2 — RL engine (metrics) · Person 4 — evaluation records"
            />
          </div>
        </Panel>
      </div>
    </ApplicationShell>
  )
}
