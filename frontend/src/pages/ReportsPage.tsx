import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import type { DataTableColumn } from '../components/ui/DataTable'
import { StatusBadge } from '../components/ui/StatusBadge'
import { filterRuns, runDetailPath, RunSummary } from '../features/reports/runHistory'
import { useServiceQuery } from '../hooks/useServiceQuery'
import { useSelectedRun } from '../hooks/useSelectedRun'
import type { TrainingRun } from '../services/trainingHistory'
import { RunContextBar } from '../features/trainingHistory/RunContextBar'
import { RunReportPanel } from '../features/trainingHistory/RunReportPanel'
import { formatUtcDate } from '../utils/datetime'
import { createEvaluationService, type EvaluationService } from '../services/evaluation'
import { EvaluationPanel } from '../features/evaluation/EvaluationPanel'
import { MonitoringPanel } from '../features/monitoring/MonitoringPanel'
import { ArchiveArt, CompareArt } from '../features/reports/ReportsIcons'
import { RunFilter } from '../features/reports/RunFilter'
import { RunHistoryTable } from '../features/reports/RunHistoryTable'
import '../features/monitoring/monitoring.css'
import '../features/reports/reports.css'

/**
 * One persisted training run as a display row. Every value is the run's own record: a missing value is `null` (shown
 * as "Not available"), never a zero or an estimate.
 */
function toSummary(run: TrainingRun): RunSummary {
  const success = run.final_metrics.success_rate
  const reward = run.final_metrics.mean_reward
  return {
    id: run.run_id,
    environment: run.environment_config_name ?? run.environment_name,
    steps: run.total_timesteps === null ? null : String(run.total_timesteps),
    successRate: typeof success === 'number' ? `${(success * 100).toFixed(1)}%` : null,
    status: run.status,
    date: run.started_at === null ? null : formatUtcDate(run.started_at),
    agent:
      run.agent_name === null
        ? null
        : `${run.agent_name}${run.agent_version === null ? '' : ` v${run.agent_version}`}`,
    reward: typeof reward === 'number' ? reward.toFixed(2) : null,
  }
}

const columns: DataTableColumn<RunSummary>[] = [
  {
    id: 'run-id',
    header: 'Run ID',
    mono: true,
    truncate: true,
    title: (run) => run.id,
    render: (run) => <Link to={runDetailPath(run.id)}>{run.id}</Link>,
  },
  {
    id: 'agent',
    header: 'Agent',
    truncate: true,
    title: (run) => run.agent ?? undefined,
    render: (run) => run.agent ?? <NotAvailable />,
  },
  {
    id: 'environment',
    header: 'Environment',
    mono: true,
    truncate: true,
    title: (run) => run.environment ?? undefined,
    render: (run) => run.environment ?? <NotAvailable />,
  },
  {
    id: 'steps',
    header: 'Steps',
    align: 'right',
    render: (run) => run.steps ?? <NotAvailable />,
  },
  {
    id: 'reward',
    header: 'Final Reward',
    align: 'right',
    render: (run) => run.reward ?? <NotAvailable />,
  },
  {
    id: 'success-rate',
    header: 'Success Rate',
    align: 'right',
    // Rendered exactly as supplied. The unit is not appended here: the metric
    // definition (fraction or percentage) is the backend's to state.
    render: (run) => run.successRate ?? <NotAvailable />,
  },
  {
    id: 'status',
    header: 'Status',
    // Rendered exactly as the backend reports it; the badge styling carries no meaning of its own.
    render: (run) =>
      run.status ? <span className="rp-status">{run.status}</span> : <NotAvailable />,
  },
  {
    id: 'date',
    header: 'Date',
    mono: true,
    render: (run) => run.date ?? <NotAvailable />,
  },
]

function NotAvailable() {
  return <span className="rp-na">Not available</span>
}

/**
 * Evaluation summary. A record is displayed only when its identifiers are
 * explicitly connected via the URL; there is no evaluation-record listing, so
 * nothing is inferred. Without a connection the section stays unavailable.
 */
function ConnectedEvaluationSummary({
  incidentId,
  evaluationId,
}: {
  incidentId: string
  evaluationId: string
}) {
  const services = useMemo(() => createEvaluationService() as EvaluationService, [])
  const evaluation = useServiceQuery(
    () => services.getEvaluation(incidentId, evaluationId),
    [services, incidentId, evaluationId],
  )
  return (
    <EvaluationPanel
      evaluation={evaluation.state}
      onReload={evaluation.reload}
      presentation="dashboard"
    />
  )
}

function EvaluationSummarySection({
  incidentId,
  evaluationId,
}: {
  incidentId: string | null
  evaluationId: string | null
}) {
  if (incidentId !== null && evaluationId !== null) {
    return <ConnectedEvaluationSummary incidentId={incidentId} evaluationId={evaluationId} />
  }
  return (
    <div role="status" className="rp-empty">
      <CompareArt />
      <span className="rp-empty__title">No evaluation records</span>
      <span className="rp-empty__text">
        An evaluation summary shows the evaluation identifier, policy fingerprint, environment
        version, episode count, seeds, per-metric results, baseline identities, and variability.
        None of that is available, so no comparison is drawn. Open this page with
        ?incidentId=&lt;incident&gt;&amp;evaluationId=&lt;record&gt; to display a recorded
        evaluation from the evaluation service.
      </span>
      <span className="rp-empty__meta">Required from: Person 4 — evaluation records</span>
    </div>
  )
}

export function ReportsPage() {
  const [searchParams] = useSearchParams()
  const incidentParam = searchParams.get('incidentId')
  const incidentId = incidentParam !== null && incidentParam.trim() !== '' ? incidentParam : null
  const evaluationParam = searchParams.get('evaluationId')
  const evaluationId =
    evaluationParam !== null && evaluationParam.trim() !== '' ? evaluationParam : null
  const evaluationConnected = incidentId !== null && evaluationId !== null
  const selected = useSelectedRun()
  const loadedRuns = useMemo(() => selected.runs.map(toSummary), [selected.runs])
  const [query, setQuery] = useState('')
  const runs = useMemo(() => filterRuns(loadedRuns, query), [loadedRuns, query])
  const filterDisabled = loadedRuns.length === 0

  return (
    <ApplicationShell>
      <div className="mon-page">
        <div className="rp-head">
          <header className="mon-header">
            <p className="mon-eyebrow">Training analytics</p>
            <h1 className="mon-title">Reports</h1>
            <p className="mon-subtitle">
              Review historical runs and compare recorded training and evaluation outcomes.
            </p>
          </header>
          <div className="rp-source">
            <StatusBadge
              label={loadedRuns.length > 0 ? 'Project run history' : 'No data source'}
              tone="quiet"
              note={evaluationConnected ? 'run history' : undefined}
            />
          </div>
        </div>

        <RunContextBar selected={selected} />

        <RunFilter
          label="Filter runs"
          value={query}
          onChange={setQuery}
          onReset={() => setQuery('')}
          placeholder="Run ID, environment, or status"
          summary={`${runs.length} of ${loadedRuns.length} recorded runs shown.`}
          scopeNote="Matches the loaded page only; it is not a server-side query."
          disabled={filterDisabled}
          disabledReason="No run records are loaded, so there is nothing to filter."
        />

        <MonitoringPanel
          title="Run History"
          icon="history"
          description="Recorded runs and their training outcomes. Status labels are taken from the backend and are never inferred from metrics."
          footer={
            <span>
              Rows are the project&apos;s persisted training runs. Per-row actions that cannot run
              are never rendered. Export is unavailable until a real export capability exists and is
              tested.
            </span>
          }
        >
          <RunHistoryTable
            caption="Recorded runs with environment, steps, success rate, backend-reported status, and date."
            columns={columns}
            rows={runs}
            getRowId={(run) => run.id}
            empty={
              <div role="status" className="rp-empty">
                <ArchiveArt />
                <span className="rp-empty__title">No run records</span>
                <span className="rp-empty__text">
                  Training history appears here once the backend records runs.
                </span>
                <span className="rp-empty__meta">
                  Nothing on this page is live, historical, or demonstration data while the history
                  source is disconnected.
                </span>
              </div>
            }
          />
        </MonitoringPanel>

        {selected.run === null ? null : (
          <MonitoringPanel
            title="Run report"
            icon="history"
            description="Built only from the selected run's persisted records and its own configuration snapshots."
          >
            <RunReportPanel selected={selected} />
          </MonitoringPanel>
        )}

        <MonitoringPanel
          title="Evaluation Summary"
          icon="compare"
          description="Baseline versus recovered comparison for a completed evaluation."
        >
          <EvaluationSummarySection incidentId={incidentId} evaluationId={evaluationId} />
        </MonitoringPanel>
      </div>
    </ApplicationShell>
  )
}
