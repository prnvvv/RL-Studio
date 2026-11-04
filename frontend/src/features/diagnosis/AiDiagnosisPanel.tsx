import { useCallback, useEffect, useMemo, useState } from 'react'
import { StatusBadge } from '../../components/ui/StatusBadge'
import {
  createDiagnosisService,
  type DiagnosisService,
  type InvestigationRecord,
  type RecoveryOption,
  type RecoveryRecommendationResult,
  type RootCauseResult,
} from '../../services/diagnosis'
import type { ServiceError } from '../../services/types'
import { formatUtcDate } from '../../utils/datetime'
import '../selfHealing/selfHealing.css'

function Evidence({ ids }: { ids: string[] }) {
  if (ids.length === 0) return <span className="sh-muted">No evidence cited.</span>
  return (
    <div className="sh-chips">
      {ids.map((id) => (
        <span key={id} className="sh-chip" title={id}>
          {id.length > 44 ? `${id.slice(0, 44)}…` : id}
        </span>
      ))}
    </div>
  )
}

function ErrorNote({ title, error }: { title: string; error: ServiceError }) {
  return (
    <p role="alert" className="sh-note sh-note--alert">
      <strong>{title}</strong> {error.detail ?? error.message}
      {error.code ? ` (${error.code})` : ''}
    </p>
  )
}

function RootCause({ record }: { record: InvestigationRecord<RootCauseResult> }) {
  const r = record.result
  return (
    <div className="sh-stack">
      <div className="sh-row">
        <StatusBadge
          label={
            r.root_cause_status === 'probable' ? 'Probable cause (inference)' : 'Cause unresolved'
          }
          tone="neutral"
          glyph="none"
        />
        <StatusBadge label="Not confirmed" tone="quiet" glyph="none" />
        <span className="sh-muted">
          {record.ai.model ? `Model ${record.ai.model}` : 'Model not recorded'}
          {record.ai.fallback_used ? ' (fallback model)' : ''} · {formatUtcDate(record.created_at)}
        </span>
      </div>
      <p className="sh-text">{r.summary}</p>

      <h4 className="sh-h3">What the records show</h4>
      {r.observed_facts.length === 0 ? (
        <p className="sh-muted">No observation was tied to a recorded reference.</p>
      ) : (
        r.observed_facts.map((f, i) => (
          <div key={i} className="sh-stack">
            <p className="sh-text">{f.statement}</p>
            <Evidence ids={f.evidence_ids} />
          </div>
        ))
      )}

      <h4 className="sh-h3">Possible causes (inferences, not facts)</h4>
      {r.hypotheses.length === 0 ? (
        <p className="sh-muted">The evidence did not support any hypothesis.</p>
      ) : (
        r.hypotheses.map((h, i) => (
          <article key={i} className="sh-card">
            <div className="sh-card__head">
              <StatusBadge label={h.component} tone="neutral" glyph="none" />
              <span className="sh-muted">
                {h.confidence === null
                  ? 'No confidence given'
                  : `Confidence ${(h.confidence * 100).toFixed(0)}% (capped)`}
                {' · '}
                {h.evidence_support}
              </span>
            </div>
            <p className="sh-text">{h.description}</p>
            <h5 className="sh-h3">Supporting evidence</h5>
            <Evidence ids={h.supporting_evidence_ids} />
            {h.contradicting_evidence_ids.length > 0 ? (
              <>
                <h5 className="sh-h3">Contradicting evidence</h5>
                <Evidence ids={h.contradicting_evidence_ids} />
              </>
            ) : null}
            {h.uncertainty ? <p className="sh-muted">Uncertainty: {h.uncertainty}</p> : null}
          </article>
        ))
      )}

      {r.missing_evidence.length > 0 ? (
        <>
          <h4 className="sh-h3">Missing evidence</h4>
          <ul className="sh-list">
            {r.missing_evidence.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </>
      ) : null}
      {r.recommended_investigation.length > 0 ? (
        <>
          <h4 className="sh-h3">Suggested next steps</h4>
          <ul className="sh-list">
            {r.recommended_investigation.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </>
      ) : null}
      {r.limitations.map((l) => (
        <p key={l} className="sh-note">
          {l}
        </p>
      ))}
      {record.warnings.map((w) => (
        <p key={w} className="sh-note">
          {w}
        </p>
      ))}
    </div>
  )
}

function Options({
  record,
  onUse,
}: {
  record: InvestigationRecord<RecoveryRecommendationResult>
  onUse?: (option: RecoveryOption) => void
}) {
  const r = record.result
  return (
    <div className="sh-stack">
      <p className="sh-note">
        These are recommendations only. Nothing below has been executed, and any state-changing
        action needs your authorization in the recovery workflow.
      </p>
      <p className="sh-text">{r.summary}</p>
      {r.options.length === 0 ? (
        <p className="sh-muted">The evidence supports no recovery option.</p>
      ) : (
        r.options.map((o, i) => (
          <article key={i} className="sh-card">
            <div className="sh-card__head">
              <div className="sh-row">
                <StatusBadge label={o.action.replace(/_/g, ' ')} tone="neutral" glyph="none" />
                <StatusBadge
                  label={
                    o.executor_supported === false
                      ? 'Cannot be executed here'
                      : 'Executable after authorization'
                  }
                  tone="quiet"
                  glyph="none"
                />
              </div>
              {o.target_checkpoint_id ? (
                <span className="sh-chip">{o.target_checkpoint_id}</span>
              ) : null}
            </div>
            <p className="sh-text">{o.reason}</p>
            {o.expected_impact ? (
              <p className="sh-muted">Expected impact: {o.expected_impact}</p>
            ) : null}
            {o.risks.length > 0 ? <p className="sh-muted">Risks: {o.risks.join('; ')}</p> : null}
            {o.preconditions.length > 0 ? (
              <p className="sh-muted">Preconditions: {o.preconditions.join('; ')}</p>
            ) : null}
            {(o.warnings ?? []).map((w) => (
              <p key={w} className="sh-note">
                {w}
              </p>
            ))}
            <Evidence ids={o.supporting_evidence_ids} />
            {onUse && o.executor_supported !== false ? (
              <div>
                <button type="button" className="sh-btn" onClick={() => onUse(o)}>
                  Review in recovery workflow
                </button>
              </div>
            ) : null}
          </article>
        ))
      )}
      {r.not_recommended.length > 0 ? (
        <>
          <h4 className="sh-h3">Not recommended</h4>
          <ul className="sh-list">
            {r.not_recommended.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </>
      ) : null}
      {r.missing_evidence.map((m) => (
        <p key={m} className="sh-note">
          Missing: {m}
        </p>
      ))}
    </div>
  )
}

interface AiDiagnosisPanelProps {
  incidentId: string
  onUseOption?: (option: RecoveryOption) => void
  service?: DiagnosisService
}

/**
 * AI diagnosis and recovery planning for one incident. Both calls are explicit user actions (they spend model
 * credits); a stored analysis of identical evidence is reused unless the user forces a re-run. Failures are shown
 * with the backend's own explanation (missing key, billing, timeout) and nothing is invented in their place.
 */
export function AiDiagnosisPanel({ incidentId, onUseOption, service }: AiDiagnosisPanelProps) {
  const api = useMemo(() => service ?? createDiagnosisService(), [service])
  const [records, setRecords] = useState<Array<InvestigationRecord<unknown>> | null>(null)
  const [loadError, setLoadError] = useState<ServiceError | null>(null)
  const [pending, setPending] = useState<'investigate' | 'recommend' | null>(null)
  const [actionError, setActionError] = useState<{ title: string; error: ServiceError } | null>(
    null,
  )
  const [note, setNote] = useState<string | null>(null)

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const result = await api.listRecords(incidentId, signal)
      if (signal?.aborted) return
      if (result.state === 'ok') {
        setRecords(result.data)
        setLoadError(null)
      } else {
        setLoadError(result.error)
      }
    },
    [api, incidentId],
  )

  useEffect(() => {
    setRecords(null)
    setActionError(null)
    setNote(null)
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  async function run(kind: 'investigate' | 'recommend', force: boolean) {
    setPending(kind)
    setActionError(null)
    setNote(null)
    const result =
      kind === 'investigate'
        ? await api.investigate(incidentId, force)
        : await api.recommend(incidentId, force)
    if (result.state === 'ok') {
      setNote(
        result.data.reused
          ? 'The stored analysis of identical evidence was reused; no model call was made.'
          : null,
      )
      await load()
    } else {
      setActionError({
        title:
          kind === 'investigate'
            ? 'The diagnosis could not be completed.'
            : 'The recovery plan could not be generated.',
        error: result.error,
      })
    }
    setPending(null)
  }

  const latestRoot = records?.find((r) => r.kind === 'root_cause') as
    InvestigationRecord<RootCauseResult> | undefined
  const latestPlan = records?.find((r) => r.kind === 'recovery_plan') as
    InvestigationRecord<RecoveryRecommendationResult> | undefined

  return (
    <div className="sh-stack">
      <p className="sh-muted">
        The analysis reads only this incident&apos;s persisted evidence. It is advisory: it never
        decides a verification verdict, never confirms a root cause and never executes a recovery.
      </p>
      <div className="sh-row">
        <button
          type="button"
          className="sh-btn sh-btn--primary"
          disabled={pending !== null}
          onClick={() => void run('investigate', false)}
        >
          {pending === 'investigate'
            ? 'Investigating…'
            : latestRoot
              ? 'Run diagnosis again'
              : 'Run AI diagnosis'}
        </button>
        <button
          type="button"
          className="sh-btn"
          disabled={pending !== null}
          onClick={() => void run('recommend', false)}
        >
          {pending === 'recommend' ? 'Planning…' : 'Generate recovery plan'}
        </button>
        {latestRoot || latestPlan ? (
          <button
            type="button"
            className="sh-btn"
            disabled={pending !== null}
            onClick={() => void run(latestPlan && !latestRoot ? 'recommend' : 'investigate', true)}
            title="Re-run even if the evidence is unchanged. This spends model credits."
          >
            Force a new analysis
          </button>
        ) : null}
      </div>
      {pending ? (
        <p role="status" className="sh-muted">
          Waiting for the analysis model. This can take a minute.
        </p>
      ) : null}
      {note ? <p className="sh-note">{note}</p> : null}
      {actionError ? <ErrorNote title={actionError.title} error={actionError.error} /> : null}
      {loadError ? (
        <ErrorNote title="Stored analyses could not be loaded." error={loadError} />
      ) : null}

      {records === null && !loadError ? <p className="sh-muted">Loading stored analyses…</p> : null}
      {records !== null && !latestRoot && !latestPlan ? (
        <div className="sh-empty" role="status">
          <span className="sh-empty__title">No analysis yet</span>
          <p className="sh-muted">
            Nothing has been analysed for this incident, so no cause or plan is shown. Requesting
            one is explicit and per incident; nothing requests it automatically unless automation is
            enabled.
          </p>
        </div>
      ) : null}

      {latestRoot ? (
        <section className="sh-stack" aria-label="Root-cause analysis">
          <h3 className="sh-h3">Root-cause analysis</h3>
          <RootCause record={latestRoot} />
        </section>
      ) : null}
      {latestPlan ? (
        <section className="sh-stack" aria-label="Recovery plan">
          <h3 className="sh-h3">Recovery plan (recommendation)</h3>
          <Options record={latestPlan} onUse={onUseOption} />
        </section>
      ) : null}
    </div>
  )
}
