import { useCallback, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import { EmptyState } from '../components/ui/EmptyState'
import { UnavailableState } from '../components/ui/UnavailableState'
import { LineChart } from '../components/charts/LineChart'
import { EventTimeline } from '../features/monitoring/EventTimeline'
import { LiveStatsPanel, LiveStatRow } from '../features/monitoring/LiveStatsPanel'
import { LiveConnectionStatus } from '../features/monitoring/LiveConnectionStatus'
import { MonitoringIcon, MonitoringPanel } from '../features/monitoring/MonitoringPanel'
import { NoRunSelected } from '../features/monitoring/NoRunSelected'
import { RunScopeField } from '../features/monitoring/RunScopeField'
import { RunLifecycleStatus } from '../features/monitoring/RunLifecycleStatus'
import { liveEventsToTimeline } from '../features/monitoring/eventPresentation'
import { LiveEventsProvider, useLiveEventsContext } from '../contexts/LiveEventsContext'
import { useRunStatus } from '../hooks/useRunStatus'
import { useSelectedRun, type SelectedRun } from '../hooks/useSelectedRun'
import { RunContextBar, reasonLabel, stamp } from '../features/trainingHistory/RunContextBar'
import { metricRows, rewardSeries, useRunMetrics } from '../features/trainingHistory/useRunMetrics'
import { createRunService } from '../services/runs'
import { formatUtcDate, formatUtcTime } from '../utils/datetime'
import '../features/monitoring/monitoring.css'

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
    <MonitoringPanel
      title="Run lifecycle"
      icon="lifecycle"
      description="Read from the run status endpoint. A failed read keeps the last recorded state and marks it stale."
    >
      <RunLifecycleStatus
        state={status.state}
        snapshotAsOf={status.lastUpdated}
        onRefresh={status.reload}
      />
    </MonitoringPanel>
  )
}

/** Lifecycle of a project run, read from the persisted run catalog (also for finished, stopped or interrupted runs). */
function CatalogLifecycleSection({ run }: { run: NonNullable<SelectedRun['run']> }) {
  const reason = reasonLabel(run)
  return (
    <MonitoringPanel
      title="Run lifecycle"
      icon="lifecycle"
      description="Read from the persisted run record, so it is the same for a live, finished, stopped or interrupted run."
    >
      <dl className="th-bar__facts" aria-label="Recorded run lifecycle">
        <div>
          <dt>Status</dt>
          <dd>
            <span className={`th-status th-status--${run.status}`}>{run.status}</span>
          </dd>
        </div>
        <div>
          <dt>Started</dt>
          <dd>{stamp(run.started_at)}</dd>
        </div>
        <div>
          <dt>Ended</dt>
          <dd>
            {run.finished_at === null
              ? run.active
                ? 'In progress'
                : 'Not recorded'
              : stamp(run.finished_at)}
          </dd>
        </div>
        {reason === null ? null : (
          <div>
            <dt>Reason</dt>
            <dd>{reason}</dd>
          </div>
        )}
        {run.error === null ? null : (
          <div>
            <dt>Error</dt>
            <dd>{run.error}</dd>
          </div>
        )}
      </dl>
    </MonitoringPanel>
  )
}

interface MonitoringContentProps {
  selected: SelectedRun
  runId: string | null
  incidentId: string | null
  onScope: (runId: string) => void
  onClearScope: () => void
}

function MonitoringContent({
  selected,
  runId,
  incidentId,
  onScope,
  onClearScope,
}: MonitoringContentProps) {
  const live = useLiveEventsContext()
  // Persisted metrics of the selected project run: history for a finished run, polled only while it is active.
  const history = useRunMetrics(selected.projectId, runId, selected.run?.active ?? false)
  const historyReady =
    history.status === 'ready' && history.metrics !== null && history.metrics.run_id === runId
  const stats = historyReady
    ? metricRows(history.metrics, selected.run?.duration_seconds ?? null)
    : liveStats
  const series = historyReady ? rewardSeries(history.metrics, runId ?? 'run') : []
  const scoped = selected.projectId !== null && runId !== null
  const linkRun = scoped ? `runId=${encodeURIComponent(runId)}` : null
  const join = (suffix: string) =>
    linkRun === null ? suffix : suffix === '' ? `?${linkRun}` : `${suffix}&${linkRun}`
  const events = liveEventsToTimeline(live.events)

  const runSuffix = runId === null ? '' : `?runId=${encodeURIComponent(runId)}`
  const incidentSuffix = incidentId === null ? '' : `?incidentId=${encodeURIComponent(incidentId)}`

  const lastBatch =
    live.lastUpdated === null
      ? null
      : [formatUtcDate(live.lastUpdated), formatUtcTime(live.lastUpdated)]
          .filter((part): part is string => part !== null)
          .join(' ')

  return (
    <div className="mon-page">
      <header className="mon-header">
        <p className="mon-eyebrow">System monitoring</p>
        <h1 className="mon-title">Monitoring</h1>
        <p className="mon-subtitle">Observe training behaviour and recorded execution events</p>
      </header>

      <RunContextBar selected={selected} />

      <section className="mon-run" aria-label="Run scope and identifier">
        <div className="mon-run__cell">
          <div className="mon-run__lead">
            <MonitoringIcon name="target" />
            <div className="mon-panel__titles">
              <h2 className="mon-panel__title">Run scope</h2>
              <p className="mon-panel__description">
                The page shows one run at a time. Events and lifecycle are only read for the
                selected identifier.
              </p>
            </div>
          </div>
          {runId === null ? null : (
            <div className="mon-run__actions">
              <button type="button" className="mon-button" onClick={onClearScope}>
                Clear run scope
              </button>
            </div>
          )}
        </div>

        <div className="mon-run__divider" aria-hidden="true" />

        <div className="mon-run__cell">
          <div className="mon-run__lead">
            <MonitoringIcon name="layers" />
            <div className="mon-panel__titles">
              <h2 className="mon-panel__title">Run identifier</h2>
              <p className="mon-panel__description">
                Subscribes this page to the run&apos;s live event stream and status endpoint.
              </p>
            </div>
          </div>
          <div className="mon-runid">
            <RunScopeField
              formId={MONITOR_SCOPE_FORM_ID}
              value={runId ?? ''}
              onSubmit={onScope}
              label="Run identifier"
            />
          </div>
          {incidentId !== null ? (
            <p className="mon-incident">
              Incident scope <code>{incidentId}</code> is carried from the link that opened this
              page. Incident records are not loaded here;{' '}
              <Link to={`/diagnosis-recovery${incidentSuffix}`}>open the incident record</Link>.
            </p>
          ) : null}
        </div>
      </section>

      <LiveConnectionStatus state={live.connection} />

      {live.connection === 'disconnected' ? (
        <div className="mon-reconnect">
          <p role="status">
            {live.transportError ??
              'The live connection stopped after its bounded retry budget. Training status is unchanged; recorded values may be stale.'}
          </p>
          <button type="button" className="mon-button" onClick={live.retry}>
            Reconnect
          </button>
        </div>
      ) : null}

      {runId === null ? null : selected.run !== null ? (
        <CatalogLifecycleSection run={selected.run} />
      ) : selected.projectId !== null && selected.status === 'loading' ? null : (
        <RunLifecycleSection runId={runId} />
      )}

      <div className="mon-main">
        <MonitoringPanel
          title="Recent Events"
          icon="layers"
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
            <NoRunSelected />
          ) : events.length === 0 ? (
            <EmptyState
              title="No events recorded for this scope"
              description="The backend replays its most recent events when the live connection opens. Nothing has been recorded for this run yet."
            />
          ) : (
            <EventTimeline events={events} />
          )}
        </MonitoringPanel>

        <div className="mon-side">
          <MonitoringPanel
            title="Live Stats"
            icon="chart"
            description="Training metrics, not held-out evaluation metrics."
          >
            <LiveStatsPanel rows={stats} />
            <p className="mon-note">
              <MonitoringIcon name="info" className="" />
              <span>
                {historyReady
                  ? 'Read from this run\u2019s persisted training record. A value the run did not record stays unavailable.'
                  : 'No run metrics are loaded, so these values stay explicitly unavailable rather than being estimated from events.'}
              </span>
            </p>
          </MonitoringPanel>

          <MonitoringPanel title="Related views" icon="link">
            <nav className="mon-links" aria-label="Related views">
              <Link to={`/training${runSuffix}`}>Training dashboard</Link>
              <Link to={`/diagnosis-recovery${join(incidentSuffix)}`}>
                Diagnosis &amp; Recovery
              </Link>
              <Link to={`/reports${join(incidentSuffix)}`}>Reports</Link>
            </nav>
            <p className="mon-hint">
              Links carry the selected run or incident scope to the destination page.
            </p>
          </MonitoringPanel>
        </div>
      </div>

      <MonitoringPanel
        title="Comparison Charts"
        icon="pulse"
        description="Reward trend against healthy, faulty, and recovered baselines. Secondary to the areas above."
      >
        <LineChart
          title="Reward versus training steps by run"
          series={series}
          xLabel="Training steps"
          yLabel="Episode reward"
        />
        <div style={{ marginTop: 'var(--space-3)' }}>
          {series.length > 0 ? (
            <p className="mon-hint">{`Episode rewards recorded for ${runId}. Baseline, faulty and recovered series need recorded evaluation records.`}</p>
          ) : (
            <UnavailableState
              title="No comparison series available"
              description="Baseline, faulty, and recovered series are drawn only from recorded evaluation and training metrics. No metrics series has been loaded."
              owner="Person 2 — RL engine (metrics) · Person 4 — evaluation records"
            />
          )}
        </div>
      </MonitoringPanel>
    </div>
  )
}

export function MonitoringPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selected = useSelectedRun()
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
          selected={selected}
          runId={runId}
          incidentId={incidentId}
          onScope={scopeToRun}
          onClearScope={clearRunScope}
        />
      </LiveEventsProvider>
    </ApplicationShell>
  )
}
