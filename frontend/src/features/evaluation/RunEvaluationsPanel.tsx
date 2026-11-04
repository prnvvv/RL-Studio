import { useMemo, useState } from 'react'
import { StatusBadge } from '../../components/ui/StatusBadge'
import {
  createRunEvaluationService,
  type RunEvaluation,
  type RunEvaluationService,
} from '../../services/runEvaluation'
import type { ServiceError } from '../../services/types'
import { formatUtcDate } from '../../utils/datetime'
import '../selfHealing/selfHealing.css'

const NA = 'Not recorded'

function num(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? NA : value.toFixed(digits)
}

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? NA : `${(value * 100).toFixed(0)}%`
}

function signed(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return NA
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}`
}

const PURPOSE_LABEL: Record<string, string> = {
  manual: 'Manual evaluation',
  auto_on_completion: 'Automatic, on run completion',
  post_recovery: 'Post-recovery policy',
  recovery_baseline: 'Recovery baseline (restored checkpoint)',
  recovery_faulty: 'Faulty reference',
}

/** One persisted evaluation. Every value is the backend's record of episodes that were actually played. */
function EvaluationCard({
  evaluation,
  service,
}: {
  evaluation: RunEvaluation
  service: RunEvaluationService
}) {
  const [episodes, setEpisodes] = useState<RunEvaluation['episodes']>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<ServiceError | null>(null)
  const s = evaluation.metrics.summary
  const v = evaluation.metrics.variability
  const ci = s?.confidence_intervals?.mean_reward

  async function showEpisodes() {
    setLoading(true)
    setError(null)
    const result = await service.getRunEvaluation(evaluation.run_id, evaluation.run_evaluation_id)
    if (result.state === 'ok') setEpisodes(result.data.episodes ?? [])
    else setError(result.error)
    setLoading(false)
  }

  return (
    <article className="sh-card" aria-label={`Evaluation ${evaluation.run_evaluation_id}`}>
      <div className="sh-card__head">
        <div className="sh-row">
          <StatusBadge
            label={evaluation.status}
            tone={evaluation.status === 'blocked' ? 'quiet' : 'strong'}
            glyph="none"
          />
          <span className="sh-text">{PURPOSE_LABEL[evaluation.purpose] ?? evaluation.purpose}</span>
        </div>
        <span className="sh-muted">{formatUtcDate(evaluation.created_at)}</span>
      </div>

      {s ? (
        <div className="sh-grid">
          <div className="sh-stat">
            <span className="sh-stat__label">Mean reward</span>
            <span className="sh-stat__value">{num(s.mean_reward)}</span>
            <span className="sh-stat__sub">
              {ci
                ? `95% CI ${num(ci.lower, 1)} to ${num(ci.upper, 1)}`
                : 'No interval (fewer than 2 episodes)'}
            </span>
          </div>
          <div className="sh-stat">
            <span className="sh-stat__label">Variability (std)</span>
            <span className="sh-stat__value">{num(v?.reward_std)}</span>
            <span className="sh-stat__sub">
              min {num(v?.reward_min, 0)} · max {num(v?.reward_max, 0)}
            </span>
          </div>
          <div className="sh-stat">
            <span className="sh-stat__label">Success rate</span>
            <span className="sh-stat__value">{pct(s.success_rate)}</span>
            <span className="sh-stat__sub">timeouts {pct(s.timeout_rate)}</span>
          </div>
          <div className="sh-stat">
            <span className="sh-stat__label">Episodes</span>
            <span className="sh-stat__value">{evaluation.episode_count}</span>
            <span className="sh-stat__sub">
              {s.failed_episode_count > 0 ? `${s.failed_episode_count} errored` : 'all valid'}
            </span>
          </div>
        </div>
      ) : (
        <p className="sh-note sh-note--alert">No metrics were produced: nothing was measured.</p>
      )}

      <dl className="sh-facts">
        <div>
          <dt>Evaluation ID</dt>
          <dd className="sh-mono">{evaluation.run_evaluation_id}</dd>
        </div>
        <div>
          <dt>Source run</dt>
          <dd className="sh-mono">{evaluation.run_id}</dd>
        </div>
        <div>
          <dt>Checkpoint</dt>
          <dd className="sh-mono">
            {evaluation.artifact_id}
            {evaluation.details.checkpoint_timestep != null
              ? ` · step ${String(evaluation.details.checkpoint_timestep)}`
              : ''}
          </dd>
        </div>
        <div>
          <dt>Policy fingerprint (file SHA-256)</dt>
          <dd className="sh-mono" title={evaluation.policy_fingerprint ?? undefined}>
            {evaluation.policy_fingerprint ? `${evaluation.policy_fingerprint.slice(0, 20)}…` : NA}
          </dd>
        </div>
        <div>
          <dt>Environment</dt>
          <dd>
            {evaluation.environment_id ?? NA} · {evaluation.environment_version ?? NA}
          </dd>
        </div>
        <div>
          <dt>Algorithm</dt>
          <dd>{evaluation.algorithm ?? NA}</dd>
        </div>
        <div>
          <dt>Seeds</dt>
          <dd className="sh-mono">
            {evaluation.seeds.length === 0
              ? NA
              : evaluation.seeds.length > 6
                ? `${evaluation.seeds.slice(0, 3).join(', ')} … ${evaluation.seeds[evaluation.seeds.length - 1]}`
                : evaluation.seeds.join(', ')}
          </dd>
        </div>
        <div>
          <dt>Baseline</dt>
          <dd>
            {evaluation.baseline
              ? evaluation.baseline.comparable
                ? `${evaluation.baseline.identity.run_evaluation_id} (${evaluation.baseline.paired ? 'paired seeds' : 'unpaired'})`
                : `${evaluation.baseline.identity.run_evaluation_id}: not comparable`
              : 'None: no comparison is drawn'}
          </dd>
        </div>
      </dl>

      {evaluation.baseline?.comparable && evaluation.baseline.deltas ? (
        <p className="sh-text">
          Versus baseline: reward {signed(evaluation.baseline.deltas.mean_reward)} · success{' '}
          {signed(evaluation.baseline.deltas.success_rate, 3)}
        </p>
      ) : evaluation.baseline ? (
        <p className="sh-note">{evaluation.baseline.reason ?? 'The baseline is not comparable.'}</p>
      ) : null}

      {evaluation.acceptance ? (
        <div className="sh-stack">
          <h4 className="sh-h3">Acceptance: {evaluation.acceptance.status}</h4>
          <ul className="sh-list">
            {evaluation.acceptance.checks.map((c) => (
              <li key={c.criterion}>
                {c.criterion.replace(/_/g, ' ')}: measured {num(c.measured)} against {c.threshold} →{' '}
                {c.outcome}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {evaluation.errors.map((e) => (
        <p key={e} role="alert" className="sh-note sh-note--alert">
          {e}
        </p>
      ))}
      {evaluation.warnings.map((w) => (
        <p key={w} className="sh-note">
          {w}
        </p>
      ))}

      {s ? (
        <div className="sh-stack">
          <div>
            <button
              type="button"
              className="sh-btn"
              onClick={() => void showEpisodes()}
              disabled={loading}
            >
              {episodes ? 'Reload episodes' : loading ? 'Loading episodes…' : 'Show episodes'}
            </button>
          </div>
          {error ? (
            <p role="alert" className="sh-note sh-note--alert">
              {error.detail ?? error.message}
            </p>
          ) : null}
          {episodes ? (
            <div className="sh-table-wrap">
              <table className="sh-table">
                <caption className="sh-muted" style={{ textAlign: 'left', padding: '6px 10px' }}>
                  Each row is one deterministic episode played from the saved policy on its seed.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Seed</th>
                    <th scope="col">Reward</th>
                    <th scope="col">Length</th>
                    <th scope="col">Success</th>
                    <th scope="col">Timed out</th>
                  </tr>
                </thead>
                <tbody>
                  {episodes.map((e) => (
                    <tr key={e.seed}>
                      <td>{e.seed}</td>
                      <td>{e.error ? `error: ${e.error}` : e.reward.toFixed(2)}</td>
                      <td>{e.episode_length}</td>
                      <td>{e.success ? 'yes' : 'no'}</td>
                      <td>{e.timed_out ? 'yes' : 'no'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </article>
  )
}

interface RunEvaluationsPanelProps {
  runId: string
  evaluations: RunEvaluation[]
  /** Whether the run has a saved checkpoint to evaluate (from the run's persisted detail). */
  checkpointCount: number
  runActive: boolean
  onChanged: () => void
  service?: RunEvaluationService
}

/**
 * Evaluate the run's saved policy against its own environment, without retraining, and keep every evaluation: a repeat
 * adds a record, never replaces one. Nothing is shown that the backend did not measure.
 */
export function RunEvaluationsPanel({
  runId,
  evaluations,
  checkpointCount,
  runActive,
  onChanged,
  service,
}: RunEvaluationsPanelProps) {
  const api = useMemo(() => service ?? createRunEvaluationService(), [service])
  const [episodes, setEpisodes] = useState('20')
  const [minimumReward, setMinimumReward] = useState('')
  const [baselineId, setBaselineId] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ServiceError | null>(null)
  const [latest, setLatest] = useState<string | null>(null)

  const count = Number(episodes)
  const validCount = Number.isInteger(count) && count >= 1 && count <= 100
  const minimum = minimumReward.trim() === '' ? null : Number(minimumReward)
  const validMinimum = minimum === null || Number.isFinite(minimum)
  const baselines = evaluations.filter((e) => e.metrics.summary !== null && e.status !== 'blocked')
  const disabled = pending || runActive || checkpointCount === 0 || !validCount || !validMinimum

  async function evaluate() {
    setPending(true)
    setError(null)
    const result = await api.evaluateRun(runId, {
      episodes: count,
      ...(minimum !== null ? { minimum_mean_reward: minimum } : {}),
      ...(baselineId !== '' ? { baseline_evaluation_id: baselineId } : {}),
    })
    if (result.state === 'ok') {
      setLatest(result.data.run_evaluation_id)
      onChanged()
    } else {
      setError(result.error)
    }
    setPending(false)
  }

  return (
    <div className="sh-stack">
      <p className="sh-muted">
        Plays the run&apos;s latest saved checkpoint for the chosen number of deterministic episodes
        on fresh seeds, in the environment it was trained in. The run is not retrained and every
        evaluation is kept.
      </p>
      <form
        className="sh-row"
        style={{ alignItems: 'flex-end' }}
        onSubmit={(event) => {
          event.preventDefault()
          if (!disabled) void evaluate()
        }}
      >
        <label className="sh-field" style={{ width: 110 }}>
          <span>Episodes (1–100)</span>
          <input
            className="sh-input"
            type="number"
            min={1}
            max={100}
            value={episodes}
            onChange={(e) => setEpisodes(e.target.value)}
            aria-invalid={!validCount}
          />
        </label>
        <label className="sh-field" style={{ width: 170 }}>
          <span>Minimum mean reward (optional)</span>
          <input
            className="sh-input"
            type="number"
            value={minimumReward}
            onChange={(e) => setMinimumReward(e.target.value)}
            placeholder="No acceptance check"
          />
        </label>
        <label className="sh-field" style={{ minWidth: 200 }}>
          <span>Compare with (optional)</span>
          <select
            className="sh-select"
            value={baselineId}
            onChange={(e) => setBaselineId(e.target.value)}
          >
            <option value="">No baseline</option>
            {baselines.map((b) => (
              <option key={b.run_evaluation_id} value={b.run_evaluation_id}>
                {formatUtcDate(b.created_at)} · mean {num(b.metrics.summary?.mean_reward, 1)}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="sh-btn sh-btn--primary" disabled={disabled}>
          {pending ? 'Evaluating…' : 'Evaluate saved policy'}
        </button>
      </form>
      {runActive ? (
        <p className="sh-note">
          This run is still training; evaluate its saved policy once it has finished.
        </p>
      ) : checkpointCount === 0 ? (
        <p className="sh-note">
          This run has no registered checkpoint, so there is no saved policy to evaluate.
        </p>
      ) : null}
      {pending ? (
        <p role="status" className="sh-muted">
          Rolling out {count} episode{count === 1 ? '' : 's'}. This runs the real policy and can
          take a moment…
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="sh-note sh-note--alert">
          <strong>The evaluation could not be completed.</strong> {error.detail ?? error.message}
        </p>
      ) : null}

      {evaluations.length === 0 ? (
        <div className="sh-empty" role="status">
          <span className="sh-empty__title">No evaluation records</span>
          <p className="sh-muted">
            This run&apos;s saved policy has not been evaluated yet. Training metrics describe the
            exploring agent; an evaluation measures the saved policy acting deterministically.
          </p>
        </div>
      ) : (
        <div className="sh-stack" aria-label="Evaluation history">
          {evaluations.map((e) => (
            <div
              key={e.run_evaluation_id}
              className={e.run_evaluation_id === latest ? 'sh-card--selected' : undefined}
            >
              <EvaluationCard evaluation={e} service={api} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
