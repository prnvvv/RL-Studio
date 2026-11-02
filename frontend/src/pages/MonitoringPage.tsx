import { useCallback, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import { Panel } from '../components/ui/Panel'
import { EmptyState } from '../components/ui/EmptyState'
import { UnavailableState } from '../components/ui/UnavailableState'
import { LineChart } from '../components/charts/LineChart'
import { EventTimeline } from '../features/monitoring/EventTimeline'
import { LiveStatsPanel, LiveStatRow } from '../features/monitoring/LiveStatsPanel'
import { LiveConnectionStatus } from '../features/monitoring/LiveConnectionStatus'
import { RunScopeField } from '../features/monitoring/RunScopeField'
import { RunLifecycleStatus } from '../features/monitoring/RunLifecycleStatus'
import { liveEventsToTimeline } from '../features/monitoring/eventPresentation'
import { LiveEventsProvider, useLiveEventsContext } from '../contexts/LiveEventsContext'
import { useRunStatus } from '../hooks/useRunStatus'
import { createRunService } from '../services/runs'
import { formatUtcDate, formatUtcTime } from '../utils/datetime'

const MONITOR_SCOPE_FORM_ID = 'monitor-run-scope'

// No run-metrics endpoint is bound (Person 2 contract pending), so every stat
// is an explicit unknown rather than a zero or an estimate.
const liveStats: LiveStatRow[] = [
  { id: 'episode', label: 'Episode', kind: 'episode', value: null },
  { id: 'total-steps', label: 'Total Steps', kind: 'steps', value: null },
  { id: 'avg-reward', label: 'Average Reward', kind: 'reward', value: null },
  { id: 'success-rate', label: 'Success Rate', kind: 'success', value: null },
  { id: 'training-time', label: 'Training Time', kind: 'time', value: null },
]

/**
 * Backend-reported lifecycle for the selected run, polled until a canonical
 * terminal state. Kept separate so the polling hook only runs with a run id.
 */
function RunLifecycleSection({ runId }: { runId: string }) {
  const runService = useMemo(createRunService, [])
  const status = useRunStatus(runId, runService)

  return (
    <Panel
      title="Run lifecycle"
      description="Read from the run status endpoint. A failed read keeps the last recorded state and marks it stale."
    >
      <RunLifecycleStatus
        state={status.state}
        snapshotAsOf={status.lastUpdated}
        onRefresh={status.reload}
      />
    </Panel>
  )
}

interface MonitoringContentProps {
  runId: string | null
  incidentId: string | null
  onScope: (runId: string) => void
  onClearScope: () => void
}

function MonitoringContent({ runId, incidentId, onScope, onClearScope }: MonitoringContentProps) {
  const live = useLiveEventsContext()
  const events = liveEventsToTimeline(live.events)

  const runSuffix = runId === null ? '' : `?runId=${encodeURIComponent(runId)}`
  const incidentSuffix = incidentId === null ? '' : `?incidentId=${encodeURIComponent(incidentId)}`

  const lastBatch =
    live.lastUpdated === null
      ? null
      : [formatUtcDate(live.lastUpdated), formatUtcTime(live.lastUpdated)]
          .filter((part): part is string => part !== null)
          .join(' ')

  const retryButton = (
    <button
      type="button"
      onClick={live.retry}
      style={{
        padding: '4px 12px',
        background: 'transparent',
        color: 'var(--text-primary)',
        border: '1px solid var(--border-primary)',
        borderRadius: 'var(--radius-sm)',
        fontSize: 'var(--text-xs)',
        fontFamily: 'var(--font-sans)',
        cursor: 'pointer',
      }}
    >
      Reconnect
    </button>
  )

  return (
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

      <Panel
        title="Run scope"
        description="The page shows one run at a time. Events and lifecycle are only read for the selected identifier."
        actions={
          runId === null ? undefined : (
            <button
              type="button"
              onClick={onClearScope}
              style={{
                padding: '4px 12px',
                background: 'transparent',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-sm)',
                fontSize: 'var(--text-xs)',
                fontFamily: 'var(--font-sans)',
                cursor: 'pointer',
              }}
            >
              Clear run scope
            </button>
          )
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <RunScopeField
            formId={MONITOR_SCOPE_FORM_ID}
            value={runId ?? ''}
            onSubmit={onScope}
            label="Run identifier"
            hint="Subscribes this page to the run's live event stream and status endpoint."
          />
          {incidentId !== null ? (
            <p
              style={{
                margin: 0,
                fontSize: 'var(--text-xs)',
                color: 'var(--text-secondary)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Incident scope <code>{incidentId}</code> is carried from the link that opened this
              page. Incident records are not loaded here;{' '}
              <Link
                to={`/diagnosis-recovery${incidentSuffix}`}
                style={{ color: 'var(--text-primary)' }}
              >
                open the incident record
              </Link>
              .
            </p>
          ) : null}
        </div>
      </Panel>

      <LiveConnectionStatus state={live.connection} />

      {live.connection === 'disconnected' ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-3)',
            flexWrap: 'wrap',
          }}
        >
          <p
            role="status"
            style={{
              margin: 0,
              fontSize: 'var(--text-xs)',
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            {live.transportError ??
              'The live connection stopped after its bounded retry budget. Training status is unchanged; recorded values may be stale.'}
          </p>
          {retryButton}
        </div>
      ) : null}

      {runId === null ? null : <RunLifecycleSection runId={runId} />}

      <div className="monitor-layout">
        <Panel
          title="Recent Events"
          description="Recorded execution events. Event types are shown exactly as recorded and are not classified in the interface yet."
          footer={
            runId === null ? undefined : (
              <span>
                {`Live window: ${live.events.length} event${live.events.length === 1 ? '' : 's'}`}
                {lastBatch === null ? ' · no batch received yet' : ` · last batch ${lastBatch}`}
                {' · no paged history endpoint is available'}
              </span>
            )
          }
        >
          {runId === null ? (
            <EmptyState
              title="No run selected"
              description="Enter a run identifier to subscribe to that run's recorded events. Nothing is inferred for an unscoped page."
            />
          ) : events.length === 0 ? (
            <EmptyState
              title="No events recorded for this scope"
              description="The backend replays its most recent events when the live connection opens. Nothing has been recorded for this run yet."
            />
          ) : (
            <EventTimeline events={events} />
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
              No run-metrics endpoint is available yet, so these values stay explicitly unavailable
              rather than being estimated from events.
            </p>
          </Panel>

          <Panel title="Related views">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <Link
                to={`/training${runSuffix}`}
                style={{
                  fontSize: 'var(--text-sm)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                Training dashboard
              </Link>
              <Link
                to={`/diagnosis-recovery${incidentSuffix}`}
                style={{
                  fontSize: 'var(--text-sm)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                Diagnosis &amp; Recovery
              </Link>
              <Link
                to={`/reports${incidentSuffix}`}
                style={{
                  fontSize: 'var(--text-sm)',
                  color: 'var(--text-primary)',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                Reports
              </Link>
            </div>
            <p
              style={{
                margin: 'var(--space-3) 0 0 0',
                fontSize: 'var(--text-xs)',
                color: 'var(--text-muted)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Links carry the selected run or incident scope to the destination page.
            </p>
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
            description="Baseline, faulty, and recovered series are drawn only from recorded evaluation and training metrics. No metrics series has been loaded."
            owner="Person 2 — RL engine (metrics) · Person 4 — evaluation records"
          />
        </div>
      </Panel>
    </div>
  )
}

export function MonitoringPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const runParam = searchParams.get('runId')
  const runId = runParam !== null && runParam.trim() !== '' ? runParam : null
  const incidentParam = searchParams.get('incidentId')
  const incidentId = incidentParam !== null && incidentParam.trim() !== '' ? incidentParam : null

  // Scope changes update the URL (not private component state) so a refresh or
  // a shared link preserves the selected run, and so the incident scope survives.
  const scopeToRun = useCallback(
    (nextRunId: string) => {
      const params = new URLSearchParams(searchParams)
      params.set('runId', nextRunId)
      setSearchParams(params)
    },
    [searchParams, setSearchParams],
  )

  const clearRunScope = useCallback(() => {
    const params = new URLSearchParams(searchParams)
    params.delete('runId')
    setSearchParams(params)
  }, [searchParams, setSearchParams])

  return (
    <ApplicationShell>
      <LiveEventsProvider runId={runId}>
        <MonitoringContent
          runId={runId}
          incidentId={incidentId}
          onScope={scopeToRun}
          onClearScope={clearRunScope}
        />
      </LiveEventsProvider>
    </ApplicationShell>
  )
}
