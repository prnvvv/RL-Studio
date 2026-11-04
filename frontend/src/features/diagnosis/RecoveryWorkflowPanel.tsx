import { useEffect, useMemo, useRef, useState } from 'react'
import { StatusBadge } from '../../components/ui/StatusBadge'
import type { Recovery, RecoveryAssessment } from '../../schemas/recovery'
import { createRecoveryService, type RecoveryService } from '../../services/recovery'
import {
  createRunEvaluationService,
  type RecoveryEvaluationResult,
  type RunEvaluationService,
} from '../../services/runEvaluation'
import type { ServiceError } from '../../services/types'
import { createIdempotencyKey } from '../recovery/idempotencyKey'
import '../selfHealing/selfHealing.css'

export interface CheckpointChoice {
  id: string
  timestep: number | null
  reason: string | null
}

export function checkpointChoices(raw: Array<Record<string, unknown>>): CheckpointChoice[] {
  return raw
    .map((c) => ({
      id: String(c.checkpoint_id ?? c.artifact_id ?? ''),
      timestep: typeof c.timestep === 'number' ? c.timestep : null,
      reason: typeof c.reason === 'string' ? c.reason : null,
    }))
    .filter((c) => c.id !== '')
    .sort((a, b) => (a.timestep ?? 0) - (b.timestep ?? 0))
}

function ErrorNote({ title, error }: { title: string; error: ServiceError }) {
  return (
    <p role="alert" className="sh-note sh-note--alert">
      <strong>{title}</strong> {error.detail ?? error.message}
    </p>
  )
}

interface RecoveryWorkflowPanelProps {
  incidentId: string
  checkpoints: CheckpointChoice[]
  /** A checkpoint suggested by a reviewed recommendation; the user still chooses and authorizes. */
  suggestedCheckpointId: string | null
  /** Recovery records already persisted for this incident, so history survives a refresh. */
  existing: Array<{
    recovery_id: string
    recovery_status: string
    recovery_strategy: string
    created_at: string
  }>
  onChanged: () => void
  recoveryService?: RecoveryService
  evaluationService?: RunEvaluationService
}

/**
 * Review, authorize, execute and validate a recovery. Four separate claims stay separate: a recommendation, an
 * eligibility assessment (computed by the backend, fail-closed), an authorized execution, and a post-recovery
 * evaluation of the policy the execution actually produced. "Executed" is never shown as "recovered": only the
 * evaluation's acceptance outcome can verify a recovery.
 */
export function RecoveryWorkflowPanel({
  incidentId,
  checkpoints,
  suggestedCheckpointId,
  existing,
  onChanged,
  recoveryService,
  evaluationService,
}: RecoveryWorkflowPanelProps) {
  const recoveries = useMemo(() => recoveryService ?? createRecoveryService(), [recoveryService])
  const evaluations = useMemo(
    () => evaluationService ?? createRunEvaluationService(),
    [evaluationService],
  )
  const [source, setSource] = useState<string>('')
  const [assessment, setAssessment] = useState<RecoveryAssessment | null>(null)
  const [recovery, setRecovery] = useState<Recovery | null>(null)
  const [authorized, setAuthorized] = useState(false)
  const [approver, setApprover] = useState('')
  const [reason, setReason] = useState('')
  const [pending, setPending] = useState<'assess' | 'execute' | 'evaluate' | null>(null)
  const [error, setError] = useState<{ title: string; error: ServiceError } | null>(null)
  const [episodes, setEpisodes] = useState('20')
  const [minSuccess, setMinSuccess] = useState('')
  const [result, setResult] = useState<RecoveryEvaluationResult | null>(null)
  const keys = useRef<Record<string, string>>({})

  // A different incident starts a clean workflow: nothing from the previous one stays on screen.
  useEffect(() => {
    setSource(suggestedCheckpointId ?? '')
    setAssessment(null)
    setRecovery(null)
    setAuthorized(false)
    setResult(null)
    setError(null)
  }, [incidentId, suggestedCheckpointId])

  const key = (scope: string) => (keys.current[scope] ??= createIdempotencyKey())

  async function assess() {
    setPending('assess')
    setError(null)
    setAssessment(null)
    setRecovery(null)
    setResult(null)
    setAuthorized(false)
    const response = await recoveries.createAssessment(incidentId, {
      recovery_strategy: 'restore_checkpoint',
      source_checkpoint_id: source,
      recovery_reason: reason.trim() === '' ? undefined : reason.trim(),
      idempotency_key: key(`assess:${incidentId}:${source}`),
    })
    if (response.state === 'ok') setAssessment(response.data)
    else setError({ title: 'The compatibility assessment failed.', error: response.error })
    setPending(null)
  }

  async function execute() {
    if (!assessment) return
    setPending('execute')
    setError(null)
    const response = await recoveries.createRecovery(incidentId, {
      assessment_id: assessment.recovery_assessment_id,
      execute: true,
      approval: { approved: true, approved_by: approver.trim(), note: reason.trim() || null },
      idempotency_key: key(`execute:${assessment.recovery_assessment_id}`),
    })
    if (response.state === 'ok') {
      setRecovery(response.data)
      onChanged()
    } else {
      setError({ title: 'The recovery could not be executed.', error: response.error })
    }
    setPending(null)
  }

  async function loadExisting(recoveryId: string) {
    const response = await recoveries.getRecovery(incidentId, recoveryId)
    if (response.state === 'ok') {
      setRecovery(response.data)
      setResult(null)
    } else {
      setError({ title: 'The recovery record could not be loaded.', error: response.error })
    }
  }

  async function evaluate() {
    if (!recovery) return
    setPending('evaluate')
    setError(null)
    const threshold = minSuccess.trim() === '' ? null : Number(minSuccess)
    const response = await evaluations.evaluateRecovery(incidentId, recovery.recovery_id, {
      episodes: Number(episodes),
      ...(threshold !== null && Number.isFinite(threshold)
        ? { acceptance_criteria: { minimum_recovered_success_rate: threshold } }
        : {}),
    })
    if (response.state === 'ok') {
      setResult(response.data)
      onChanged()
    } else {
      setError({
        title: 'The post-recovery evaluation could not be completed.',
        error: response.error,
      })
    }
    setPending(null)
  }

  const ineligible = assessment?.recovery_eligibility === 'ineligible'
  const canExecute =
    assessment !== null &&
    !ineligible &&
    authorized &&
    approver.trim() !== '' &&
    pending === null &&
    recovery === null
  const episodesValid =
    Number.isInteger(Number(episodes)) && Number(episodes) >= 1 && Number(episodes) <= 100
  const thresholdValid =
    minSuccess.trim() === '' || (Number(minSuccess) >= 0 && Number(minSuccess) <= 1)

  return (
    <div className="sh-stack">
      <p className="sh-muted">
        Restoring a checkpoint is the one recovery action the executor can run. It copies the chosen
        checkpoint to a new recovered artifact; the original is never modified. Eligibility is
        computed by the backend and fails closed: an assessment that is ineligible cannot be
        authorized.
      </p>

      {existing.length > 0 ? (
        <div className="sh-stack">
          <h4 className="sh-h3">Recovery history for this incident</h4>
          <ul className="sh-list">
            {existing.map((r) => (
              <li key={r.recovery_id}>
                <span className="sh-mono">{r.recovery_id}</span> ·{' '}
                {r.recovery_strategy.replace(/_/g, ' ')} · {r.recovery_status}{' '}
                <button
                  type="button"
                  className="sh-btn"
                  onClick={() => void loadExisting(r.recovery_id)}
                >
                  Open
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <h4 className="sh-h3">1. Choose a checkpoint and assess</h4>
      {checkpoints.length === 0 ? (
        <p className="sh-note">This run has no checkpoints, so there is nothing to restore.</p>
      ) : (
        <div className="sh-row" style={{ alignItems: 'flex-end' }}>
          <label className="sh-field" style={{ minWidth: 260 }}>
            <span>Checkpoint to restore</span>
            <select
              className="sh-select"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              <option value="">Select a checkpoint…</option>
              {checkpoints.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id}
                  {c.timestep !== null ? ` · step ${c.timestep}` : ''}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="sh-btn sh-btn--primary"
            disabled={source === '' || pending !== null}
            onClick={() => void assess()}
          >
            {pending === 'assess' ? 'Assessing…' : 'Assess compatibility'}
          </button>
        </div>
      )}

      {assessment ? (
        <section className="sh-card" aria-label="Compatibility assessment">
          <div className="sh-card__head">
            <StatusBadge
              label={`Eligibility: ${assessment.recovery_eligibility.replace(/_/g, ' ')}`}
              tone="neutral"
              glyph="none"
            />
            <span className="sh-mono">{assessment.recovery_assessment_id}</span>
          </div>
          <div className="sh-table-wrap">
            <table className="sh-table">
              <caption className="sh-muted" style={{ textAlign: 'left', padding: '6px 10px' }}>
                Preflight checks computed by the recovery service.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Check</th>
                  <th scope="col">Outcome</th>
                  <th scope="col">Detail</th>
                </tr>
              </thead>
              <tbody>
                {assessment.compatibility.map((c) => (
                  <tr key={c.name}>
                    <td>{c.name.replace(/_/g, ' ')}</td>
                    <td>{c.outcome}</td>
                    <td style={{ whiteSpace: 'normal' }}>{c.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {assessment.lineage_gaps.length > 0 ? (
            <p className="sh-note">Lineage gaps: {assessment.lineage_gaps.join('; ')}.</p>
          ) : null}
          {assessment.warnings.map((w) => (
            <p key={w} className="sh-note">
              {w}
            </p>
          ))}
          {ineligible ? (
            <p role="alert" className="sh-note sh-note--alert">
              This checkpoint is ineligible: at least one check failed, so no recovery can be
              authorized for it. Nothing was changed. Choose a checkpoint the incident&apos;s
              lineage places outside the affected interval, or investigate further.
            </p>
          ) : null}
        </section>
      ) : null}

      {assessment && !ineligible ? (
        <>
          <h4 className="sh-h3">2. Authorize and execute</h4>
          <div className="sh-stack">
            <label className="sh-field" style={{ maxWidth: 320 }}>
              <span>Your name (recorded with the approval)</span>
              <input
                className="sh-input"
                value={approver}
                onChange={(e) => setApprover(e.target.value)}
                maxLength={80}
              />
            </label>
            <label className="sh-field">
              <span>Reason / note (optional)</span>
              <textarea
                className="sh-textarea"
                rows={2}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={500}
              />
            </label>
            <label className="sh-row">
              <input
                type="checkbox"
                checked={authorized}
                onChange={(e) => setAuthorized(e.target.checked)}
              />
              <span className="sh-text">
                I authorize restoring checkpoint <span className="sh-mono">{source}</span> into a
                new recovered artifact for this incident.
              </span>
            </label>
            <div>
              <button
                type="button"
                className="sh-btn sh-btn--primary"
                disabled={!canExecute}
                onClick={() => void execute()}
              >
                {pending === 'execute' ? 'Executing…' : 'Execute authorized recovery'}
              </button>
            </div>
          </div>
        </>
      ) : null}

      {recovery ? (
        <section className="sh-card" aria-label="Recovery record">
          <div className="sh-card__head">
            <StatusBadge
              label={`Recovery ${recovery.recovery_status}`}
              tone={
                recovery.recovery_status === 'completed' || recovery.recovery_status === 'evaluated'
                  ? 'strong'
                  : 'quiet'
              }
              glyph="none"
            />
            <span className="sh-mono">{recovery.recovery_id}</span>
          </div>
          {recovery.failure_reason ? (
            <p role="alert" className="sh-note sh-note--alert">
              {recovery.failure_reason}
            </p>
          ) : null}
          <ul className="sh-list">
            {recovery.executed_actions.map((a) => (
              <li key={a.action}>
                {a.action.replace(/_/g, ' ')}: {a.status}
                {a.detail ? ` — ${a.detail}` : ''}
              </li>
            ))}
          </ul>
          {recovery.recovery_artifact_id ? (
            <p className="sh-text">
              Recovered artifact: <span className="sh-mono">{recovery.recovery_artifact_id}</span>
            </p>
          ) : (
            <p className="sh-muted">No recovered artifact was produced.</p>
          )}
          <p className="sh-note">
            Execution completing is not recovery success. Only the evaluation of the recovered
            policy, against acceptance criteria, can verify it.
          </p>
        </section>
      ) : null}

      {recovery && recovery.recovery_artifact_id ? (
        <>
          <h4 className="sh-h3">3. Validate the recovered policy</h4>
          <form
            className="sh-row"
            style={{ alignItems: 'flex-end' }}
            onSubmit={(e) => {
              e.preventDefault()
              if (episodesValid && thresholdValid && pending === null) void evaluate()
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
              />
            </label>
            <label className="sh-field" style={{ width: 200 }}>
              <span>Minimum success rate (0–1)</span>
              <input
                className="sh-input"
                type="number"
                step="0.05"
                min={0}
                max={1}
                value={minSuccess}
                onChange={(e) => setMinSuccess(e.target.value)}
                placeholder="No acceptance criterion"
              />
            </label>
            <button
              type="submit"
              className="sh-btn sh-btn--primary"
              disabled={!episodesValid || !thresholdValid || pending !== null}
            >
              {pending === 'evaluate' ? 'Evaluating…' : 'Evaluate recovered policy'}
            </button>
          </form>
          {pending === 'evaluate' ? (
            <p role="status" className="sh-muted">
              Rolling out the recovered policy on held-out seeds…
            </p>
          ) : null}
        </>
      ) : null}

      {result ? (
        <section className="sh-card" aria-label="Post-recovery evaluation">
          <div className="sh-card__head">
            <StatusBadge
              label={
                result.evaluation.recovery_verified ? 'Recovery verified' : 'Recovery not verified'
              }
              tone={result.evaluation.recovery_verified ? 'strong' : 'quiet'}
              glyph="none"
            />
            <span className="sh-muted">Evaluation {result.evaluation.evaluation_status}</span>
          </div>
          <div className="sh-grid">
            <div className="sh-stat">
              <span className="sh-stat__label">Recovered mean reward</span>
              <span className="sh-stat__value">
                {result.evaluation.recovered_mean_reward?.toFixed(2) ?? 'Not recorded'}
              </span>
            </div>
            <div className="sh-stat">
              <span className="sh-stat__label">Restored-checkpoint baseline</span>
              <span className="sh-stat__value">
                {result.evaluation.baseline_mean_reward?.toFixed(2) ?? 'Not recorded'}
              </span>
            </div>
            <div className="sh-stat">
              <span className="sh-stat__label">Recovered success rate</span>
              <span className="sh-stat__value">
                {result.evaluation.recovered_success_rate === null
                  ? 'Not recorded'
                  : `${(result.evaluation.recovered_success_rate * 100).toFixed(0)}%`}
              </span>
            </div>
            <div className="sh-stat">
              <span className="sh-stat__label">Episodes / seeds</span>
              <span className="sh-stat__value">{result.evaluation.episode_count ?? 0}</span>
              <span className="sh-stat__sub">
                {result.evaluation.seeds.slice(0, 3).join(', ')}…
              </span>
            </div>
          </div>
          <p className="sh-muted">
            The recovered policy evaluated is artifact{' '}
            <span className="sh-mono">{result.recovered_policy.artifact_id}</span>
            {result.recovered_policy.policy_fingerprint
              ? `, fingerprint ${result.recovered_policy.policy_fingerprint.slice(0, 16)}…`
              : ''}
            .
          </p>
          {result.note ? <p className="sh-note">{result.note}</p> : null}
          {result.evaluation.errors.map((e) => (
            <p key={e} role="alert" className="sh-note sh-note--alert">
              {e}
            </p>
          ))}
          {result.evaluation.warnings.map((w) => (
            <p key={w} className="sh-note">
              {w}
            </p>
          ))}
        </section>
      ) : null}

      {error ? <ErrorNote title={error.title} error={error.error} /> : null}
    </div>
  )
}
