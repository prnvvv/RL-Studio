import { LineChart } from '../../components/charts/LineChart'
import type { SelectedRun } from '../../hooks/useSelectedRun'
import { reasonLabel, stamp } from './RunContextBar'
import { rewardSeries, useRunMetrics } from './useRunMetrics'

function Row({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {value === null || value === undefined || value === '' ? 'Not recorded' : String(value)}
      </dd>
    </div>
  )
}

function params(
  snapshot: Record<string, unknown> | undefined,
  key: string,
): Array<[string, string]> {
  const value = snapshot?.[key]
  if (typeof value !== 'object' || value === null) return []
  return Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, JSON.stringify(v)])
}

/**
 * A report for exactly one run, built only from that run's persisted records: its own configuration snapshots (not the
 * agent's current configuration), recorded final metrics, recorded episode rewards, and the verification, incident and
 * recovery records linked to it. Nothing from the newest run, and nothing synthesised, appears here.
 */
export function RunReportPanel({ selected }: { selected: SelectedRun }) {
  const { run, detail, runId, projectId } = selected
  const metrics = useRunMetrics(projectId, runId, run?.active ?? false)
  if (run === null || detail === null) return null
  const ready = metrics.status === 'ready' && metrics.metrics?.run_id === run.run_id
  const series = ready ? rewardSeries(metrics.metrics, run.run_id) : []
  const final = run.final_metrics
  const agentParams = params(detail.snapshots.agent, 'agent_params')
  const envParams = params(detail.snapshots.environment, 'env_params')

  return (
    <div className="th-report" aria-label={`Report for run ${run.run_id}`}>
      {run.active ? (
        <p role="status" className="mon-hint">
          This run is still in progress, so the report below is a partial snapshot of what has been
          recorded so far.
        </p>
      ) : null}
      <h3 className="mon-panel__title">Training summary</h3>
      <dl className="th-bar__facts">
        <Row label="Run" value={run.run_id} />
        <Row label="Status" value={run.status} />
        <Row label="Ended" value={reasonLabel(run)} />
        <Row label="Started" value={stamp(run.started_at)} />
        <Row label="Finished" value={run.finished_at === null ? null : stamp(run.finished_at)} />
        <Row label="Duration (s)" value={run.duration_seconds?.toFixed(1)} />
        <Row label="Timesteps" value={run.total_timesteps} />
        <Row label="Episodes" value={run.total_episodes} />
        <Row label="Mean reward" value={final.mean_reward?.toFixed(2)} />
        <Row label="Best reward" value={final.best_reward?.toFixed(2)} />
        <Row label="Seed" value={run.seed} />
      </dl>

      <h3 className="mon-panel__title">Configuration used by this run</h3>
      <dl className="th-bar__facts">
        <Row
          label="Agent"
          value={`${run.agent_name ?? run.algorithm ?? ''}${run.agent_version === null ? '' : ` v${run.agent_version}`}`}
        />
        <Row label="Environment" value={run.environment_config_name ?? run.environment_name} />
        <Row label="Experiment" value={run.experiment_name} />
        {agentParams.map(([k, v]) => (
          <Row key={`a-${k}`} label={`agent · ${k}`} value={v} />
        ))}
        {envParams.map(([k, v]) => (
          <Row key={`e-${k}`} label={`environment · ${k}`} value={v} />
        ))}
      </dl>

      <h3 className="mon-panel__title">Reward progression</h3>
      {series.length > 0 ? (
        <LineChart
          title={`Episode reward · ${run.run_id}`}
          series={series}
          xLabel="Training steps"
          yLabel="Episode reward"
        />
      ) : (
        <p role="status" className="mon-hint">
          {metrics.status === 'loading'
            ? 'Loading the recorded episodes…'
            : 'No episode rewards were recorded for this run.'}
        </p>
      )}

      <h3 className="mon-panel__title">Verification, incidents and recovery</h3>
      <ul aria-label="Linked records">
        <li>
          {detail.verifications.length === 0
            ? 'No verification has been run against this run.'
            : `Verifications: ${detail.verifications.map((v) => `${v.verification_id} (${v.overall_status})`).join(', ')}`}
        </li>
        <li>
          {detail.incidents.length === 0
            ? 'No incidents were recorded for this run.'
            : `Incidents: ${detail.incidents.map((i) => `${i.incident_id} (${i.status})`).join(', ')}`}
        </li>
        <li>
          {detail.recoveries.length === 0
            ? 'No recovery history for this run.'
            : `Recoveries: ${detail.recoveries.map((r) => `${r.recovery_id} (${r.recovery_status})`).join(', ')}`}
        </li>
      </ul>

      <h3 className="mon-panel__title">Checkpoints</h3>
      <p>
        {detail.checkpoints.length === 0
          ? 'No checkpoints were recorded for this run.'
          : `${detail.checkpoints.length} checkpoint reference${detail.checkpoints.length === 1 ? '' : 's'} recorded.`}
      </p>
    </div>
  )
}
