import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { LineChart } from '../../components/charts/LineChart'
import { StatusBadge } from '../../components/ui/StatusBadge'
import type { SelectedRun } from '../../hooks/useSelectedRun'
import { formatUtcDate } from '../../utils/datetime'
import { RunEvaluationsPanel } from '../evaluation/RunEvaluationsPanel'
import { reasonLabel } from './RunContextBar'
import { rewardSeries, useRunMetrics } from './useRunMetrics'
import '../selfHealing/selfHealing.css'

const NA = 'Not recorded'

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="rr-section" aria-label={title}>
      <div className="rr-section__head">
        <h3 className="rr-section__title">{title}</h3>
        {hint ? <span className="sh-muted">{hint}</span> : null}
      </div>
      {children}
    </section>
  )
}

function Stat({
  label,
  value,
  sub,
}: {
  label: string
  value: string | number | null | undefined
  sub?: string
}) {
  const empty = value === null || value === undefined || value === ''
  return (
    <div className="sh-stat">
      <span className="sh-stat__label">{label}</span>
      <span
        className="sh-stat__value"
        style={empty ? { fontSize: 'var(--text-sm)', fontWeight: 400 } : undefined}
      >
        {empty ? NA : String(value)}
      </span>
      {sub ? <span className="sh-stat__sub">{sub}</span> : null}
    </div>
  )
}

function Facts({ rows }: { rows: Array<[string, string | number | null | undefined]> }) {
  return (
    <dl className="sh-facts">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value === null || value === undefined || value === '' ? NA : String(value)}</dd>
        </div>
      ))}
    </dl>
  )
}

function entries(
  snapshot: Record<string, unknown> | undefined,
  key: string,
): Array<[string, string]> {
  const value = snapshot?.[key]
  if (typeof value !== 'object' || value === null) return []
  return Object.entries(value as Record<string, unknown>).map(([k, v]) => [
    k.replace(/_/g, ' '),
    String(v),
  ])
}

function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="sh-empty" role="status">
      <span className="sh-empty__title">{title}</span>
      <p className="sh-muted">{children}</p>
    </div>
  )
}

/**
 * A report for exactly one run, built only from that run's persisted records: its own configuration snapshots (not the
 * agent's current configuration), recorded training metrics, policy evaluations, and the verification, incident,
 * recovery and checkpoint records linked to it. Nothing from another run, and nothing synthesised, appears here.
 */
export function RunReportPanel({ selected }: { selected: SelectedRun }) {
  const { run, detail, runId, projectId } = selected
  const metrics = useRunMetrics(projectId, runId, run?.active ?? false)
  if (run === null || detail === null) return null
  const ready = metrics.status === 'ready' && metrics.metrics?.run_id === run.run_id
  const series = ready ? rewardSeries(metrics.metrics, run.run_id) : []
  const final = run.final_metrics
  const agentParams = entries(detail.snapshots.agent, 'agent_params')
  const envParams = entries(detail.snapshots.environment, 'env_params')
  const trainingParams = Object.entries(detail.snapshots.training ?? {}).map(
    ([k, v]): [string, string] => [k.replace(/_/g, ' '), String(v)],
  )
  const evaluations = detail.evaluations ?? []
  const diagnosisHref = (incidentId: string) =>
    `/diagnosis-recovery?runId=${encodeURIComponent(run.run_id)}&incidentId=${encodeURIComponent(incidentId)}`

  return (
    <div className="rr" aria-label={`Report for run ${run.run_id}`}>
      {run.active ? (
        <p role="status" className="sh-note">
          This run is still in progress, so the report is a partial snapshot of what has been
          recorded so far.
        </p>
      ) : null}

      <Section title="Overview" hint={run.run_id}>
        <div className="sh-grid">
          <div className="sh-stat">
            <span className="sh-stat__label">Status</span>
            <span className="sh-stat__value">{run.status}</span>
            <span className="sh-stat__sub">{reasonLabel(run)}</span>
          </div>
          <Stat
            label="Mean reward (training)"
            value={final.mean_reward?.toFixed(2)}
            sub="across all training episodes"
          />
          <Stat label="Best episode reward" value={final.best_reward?.toFixed(2)} />
          <Stat
            label="Success rate (training)"
            value={
              typeof final.success_rate === 'number'
                ? `${(final.success_rate * 100).toFixed(1)}%`
                : null
            }
          />
          <Stat label="Timesteps" value={run.total_timesteps} />
          <Stat label="Episodes" value={run.total_episodes} />
          <Stat
            label="Duration"
            value={run.duration_seconds === null ? null : `${run.duration_seconds.toFixed(0)} s`}
          />
        </div>
        <Facts
          rows={[
            [
              'Agent',
              `${run.agent_name ?? run.algorithm ?? ''}${run.agent_version === null ? '' : ` v${run.agent_version}`}`,
            ],
            ['Environment', run.environment_config_name ?? run.environment_name],
            ['Experiment', run.experiment_name],
            ['Seed', run.seed],
            ['Started', run.started_at === null ? null : formatUtcDate(run.started_at)],
            ['Finished', run.finished_at === null ? null : formatUtcDate(run.finished_at)],
          ]}
        />
      </Section>

      <Section
        title="Reward progression"
        hint="Training-time episode rewards: the exploring agent, not the saved policy."
      >
        {series.length > 0 ? (
          <LineChart
            title={`Episode reward · ${run.run_id}`}
            series={series}
            xLabel="Training steps"
            yLabel="Episode reward"
          />
        ) : (
          <Empty
            title={
              metrics.status === 'loading' ? 'Loading episodes' : 'No episode rewards recorded'
            }
          >
            {metrics.status === 'loading'
              ? 'Reading the recorded episodes for this run…'
              : 'No episode reward was recorded for this run, so no curve is drawn.'}
          </Empty>
        )}
      </Section>

      <Section title="Configuration used by this run" hint="Snapshots taken when the run started.">
        <div className="rr-two">
          {[
            ['Agent parameters', agentParams],
            ['Environment parameters', envParams],
            ['Training settings', trainingParams],
          ].map(([title, rows]) => (
            <div key={title as string} className="sh-card">
              <h4 className="sh-h3">{title as string}</h4>
              {(rows as Array<[string, string]>).length === 0 ? (
                <p className="sh-muted">No snapshot was recorded.</p>
              ) : (
                <Facts rows={rows as Array<[string, string]>} />
              )}
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="Policy evaluations"
        hint="The saved policy acting deterministically on held-out seeds."
      >
        <RunEvaluationsPanel
          runId={run.run_id}
          evaluations={evaluations}
          checkpointCount={detail.checkpoints.length}
          runActive={run.active}
          onChanged={selected.reload}
        />
      </Section>

      <Section title="Verification" hint="Deterministic verdicts against confirmed requirements.">
        {detail.verifications.length === 0 ? (
          <Empty title="No verification yet">
            No requirement has been verified against this run. Confirm a requirement in the project
            workspace and verify it; a missing result is never a pass.
          </Empty>
        ) : (
          <div className="sh-table-wrap">
            <table className="sh-table">
              <thead>
                <tr>
                  <th scope="col">Verification</th>
                  <th scope="col">Overall</th>
                  <th scope="col">Recorded</th>
                </tr>
              </thead>
              <tbody>
                {detail.verifications.map((v) => (
                  <tr key={v.verification_id}>
                    <td className="sh-mono">{v.verification_id}</td>
                    <td>{v.overall_status}</td>
                    <td>{formatUtcDate(v.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Incidents and diagnosis" hint="Opened by a failing final verification.">
        {detail.incidents.length === 0 ? (
          <Empty title="No incidents">No incident was recorded for this run.</Empty>
        ) : (
          <div className="sh-stack">
            {detail.incidents.map((i) => (
              <article key={i.incident_id} className="sh-card">
                <div className="sh-card__head">
                  <span className="sh-mono">{i.incident_id}</span>
                  <div className="sh-row">
                    {i.severity ? (
                      <StatusBadge label={`severity ${i.severity}`} tone="neutral" glyph="none" />
                    ) : null}
                    <StatusBadge label={i.status} tone="quiet" glyph="none" />
                  </div>
                </div>
                <p className="sh-text">{i.summary ?? 'No summary was recorded.'}</p>
                <div className="sh-row">
                  <span className="sh-muted">
                    {i.investigations === 0
                      ? 'No AI analysis stored'
                      : `${i.investigations} AI analys${i.investigations === 1 ? 'is' : 'es'} stored (advisory)`}
                  </span>
                  <Link to={diagnosisHref(i.incident_id)}>Open in Diagnosis &amp; Recovery</Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </Section>

      <Section title="Recovery" hint="Executed recoveries; success needs a passing evaluation.">
        {detail.recoveries.length === 0 ? (
          <Empty title="No recovery history">
            No recovery was planned or executed for this run.
          </Empty>
        ) : (
          <div className="sh-table-wrap">
            <table className="sh-table">
              <thead>
                <tr>
                  <th scope="col">Recovery</th>
                  <th scope="col">Incident</th>
                  <th scope="col">Strategy</th>
                  <th scope="col">Status</th>
                  <th scope="col">Recorded</th>
                </tr>
              </thead>
              <tbody>
                {detail.recoveries.map((r) => (
                  <tr key={r.recovery_id}>
                    <td className="sh-mono">{r.recovery_id}</td>
                    <td className="sh-mono">{r.incident_id}</td>
                    <td>{r.recovery_strategy.replace(/_/g, ' ')}</td>
                    <td>{r.recovery_status}</td>
                    <td>{formatUtcDate(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Checkpoints and artifacts">
        {detail.checkpoints.length === 0 ? (
          <Empty title="No checkpoints">No checkpoint was recorded for this run.</Empty>
        ) : (
          <div className="sh-table-wrap">
            <table className="sh-table">
              <thead>
                <tr>
                  <th scope="col">Checkpoint</th>
                  <th scope="col">Step</th>
                  <th scope="col">Reason</th>
                  <th scope="col">SHA-256</th>
                </tr>
              </thead>
              <tbody>
                {detail.checkpoints.map((c, i) => (
                  <tr key={String(c.checkpoint_id ?? i)}>
                    <td className="sh-mono">{String(c.checkpoint_id ?? NA)}</td>
                    <td>{c.timestep === undefined ? NA : String(c.timestep)}</td>
                    <td>{c.reason === undefined || c.reason === null ? NA : String(c.reason)}</td>
                    <td className="sh-mono">
                      {typeof c.sha256 === 'string' ? `${c.sha256.slice(0, 16)}…` : NA}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  )
}
