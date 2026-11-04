import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ChangeEvent } from 'react'
import { Link } from 'react-router-dom'
import type {
  ProjectDocument,
  ProjectRequirement,
  ProjectRun,
  ProjectStage,
  ProjectVerificationRow,
  VerifyResult,
} from '../../schemas/projects'
import { ACCEPTED_DOCUMENT_EXTENSIONS } from '../../schemas/projects'
import { createProjectService } from '../../services/projects'
import type { ProjectService } from '../../services/projects'
import { STAGE_LABEL, documentProblem, formatWhen } from './projectFormat'

const ACTIVE_RUN = ['running', 'paused', 'stopping']
const REFRESH_MS = 5000
const defaultService = createProjectService()

function stageFor(runs: ProjectRun[], runId: string): ProjectStage {
  if (runId) {
    const run = runs.find((r) => r.run_id === runId)
    return run && ACTIVE_RUN.includes(run.status) ? 'during_training' : 'post_training'
  }
  return runs.length === 0 ? 'pre_training' : 'project_level'
}

const OPERATORS = ['>=', '<=', '>', '<', '==', '!=']

function RequirementRow({
  requirement,
  busy,
  onConfirm,
  onReject,
  onCritical,
}: {
  requirement: ProjectRequirement
  busy: boolean
  onConfirm: (overrides?: Record<string, unknown>) => void
  onReject: () => void
  onCritical: (critical: boolean) => void
}) {
  const [operator, setOperator] = useState('>=')
  const [value, setValue] = useState('')
  const r = requirement
  const open = r.lifecycle_status === 'draft' || r.lifecycle_status === 'needs_clarification'
  const needsInput = r.lifecycle_status === 'needs_clarification'
  const reasons = [...(r.validation.reasons ?? []), ...(r.validation.warnings ?? [])]

  return (
    <li>
      <div className="pw-line">
        <span className="pw-text">{r.source_statement}</span>
      </div>
      <div className="pw-line">
        <span
          className={`pw-badge${r.confirmation_status === 'confirmed' ? ' pw-badge--strong' : ''}`}
        >
          {r.confirmation_status === 'confirmed'
            ? 'Confirmed'
            : r.confirmation_status === 'rejected'
              ? 'Rejected'
              : 'Proposed'}
        </span>
        <span className="pw-badge">{r.category}</span>
        <span className="pw-badge">rev {r.requirement_revision}</span>
        {r.superseded ? <span className="pw-badge pw-badge--dashed">superseded</span> : null}
        {r.stage ? <span className="pw-badge">{STAGE_LABEL[r.stage]}</span> : null}
        {r.source.filename ? <span className="pw-badge pw-mono">{r.source.filename}</span> : null}
        {r.latest_verification ? (
          <span className="pw-badge pw-badge--strong">
            Last: {r.latest_verification.status.toUpperCase()}
          </span>
        ) : null}
      </div>
      <span className="pw-muted">
        {r.description}
        {r.comparison_operator != null && r.expected_value != null
          ? ` — ${r.comparison_operator} ${String(r.expected_value)}`
          : ''}
      </span>
      {r.awaiting_run_evidence ? (
        <p className="pw-note">
          Saved for this project. It can only be verified once a run provides evidence.
        </p>
      ) : null}
      {r.clarification_question ? (
        <p className="pw-note">Needs your input: {r.clarification_question}</p>
      ) : null}
      {r.conflicts_with.length > 0 ? (
        <p className="pw-note">
          Contradicts another requirement ({r.conflicts_with.length}). Reject one before confirming.
        </p>
      ) : null}
      {open && reasons.length > 0 ? <span className="pw-muted">{reasons.join(' · ')}</span> : null}
      {open ? (
        <div className="pw-actions">
          {needsInput ? (
            <>
              <select
                aria-label="Comparison"
                className="pw-select"
                style={{ width: 'auto' }}
                value={operator}
                onChange={(e) => setOperator(e.target.value)}
              >
                {OPERATORS.map((op) => (
                  <option key={op} value={op}>
                    {op}
                  </option>
                ))}
              </select>
              <input
                aria-label="Expected value"
                className="pw-select"
                style={{ width: 110 }}
                inputMode="decimal"
                value={value}
                onChange={(e) => setValue(e.target.value)}
              />
            </>
          ) : null}
          <button
            type="button"
            className="pw-button pw-button--solid"
            disabled={
              busy ||
              (needsInput && Number.isNaN(Number(value))) ||
              (needsInput && value.trim() === '')
            }
            onClick={() =>
              onConfirm(
                needsInput
                  ? { comparison_operator: operator, expected_value: Number(value) }
                  : undefined,
              )
            }
          >
            Confirm
          </button>
          <button type="button" className="pw-button" disabled={busy} onClick={onReject}>
            Reject
          </button>
        </div>
      ) : null}
      {r.confirmation_status === 'confirmed' && !r.superseded ? (
        <label className="pw-line">
          <input
            type="checkbox"
            checked={r.critical_safety === true}
            disabled={busy}
            onChange={(e) => onCritical(e.target.checked)}
          />
          <span className="pw-text">Critical safety rule</span>
          <span className="pw-muted">
            A violation seen while training is still running raises an incident immediately.
            Otherwise it stays provisional until the run finishes.
          </span>
        </label>
      ) : null}
    </li>
  )
}

export interface ProjectIntentPanelProps {
  projectId: string
  service?: ProjectService
  /** Called after anything that changes the project's counts, so the page header can refresh. */
  onChanged?: () => void
}

/**
 * Project-level Intent & Verification. The same panel serves all three lifecycle moments: before training (no run
 * is selected), during training (an active run is selected) and after it (a finished run). Interpretation,
 * confirmation and PASS/FAIL/UNKNOWN all come from the existing Person 3 pipeline; this panel only chooses when.
 */
export function ProjectIntentPanel({
  projectId,
  service = defaultService,
  onChanged,
}: ProjectIntentPanelProps) {
  const [requirements, setRequirements] = useState<ProjectRequirement[]>([])
  const [documents, setDocuments] = useState<ProjectDocument[]>([])
  const [runs, setRuns] = useState<ProjectRun[]>([])
  const [history, setHistory] = useState<ProjectVerificationRow[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  const [statement, setStatement] = useState('')
  const [selectedDocs, setSelectedDocs] = useState<string[]>([])
  const [runId, setRunId] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [verifyRunId, setVerifyRunId] = useState('')
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null)

  const refresh = useCallback(async () => {
    const [reqs, docs, rs, hist] = await Promise.all([
      service.listRequirements(projectId),
      service.listDocuments(projectId),
      service.listRuns(projectId),
      service.listVerifications(projectId),
    ])
    const failed = [reqs, docs, rs, hist].find((r) => r.state === 'error')
    if (failed && failed.state === 'error') {
      setLoadError(failed.error.message)
    } else {
      setLoadError(null)
    }
    if (reqs.state === 'ok') setRequirements(reqs.data)
    if (docs.state === 'ok') setDocuments(docs.data)
    if (rs.state === 'ok') setRuns(rs.data)
    if (hist.state === 'ok') setHistory(hist.data)
    setLoaded(true)
  }, [projectId, service])

  useEffect(() => {
    // Subscribing to the backend (an external system): the state is set when the response arrives.
    void refresh()
  }, [refresh])

  const hasActiveRun = runs.some((r) => ACTIVE_RUN.includes(r.status))
  useEffect(() => {
    if (!hasActiveRun) return
    const timer = setInterval(() => void refresh(), REFRESH_MS)
    return () => clearInterval(timer)
  }, [hasActiveRun, refresh])

  const stage = stageFor(runs, runId)
  const live = useMemo(
    () => requirements.filter((r) => r.lifecycle_status !== 'rejected'),
    [requirements],
  )
  const confirmed = useMemo(
    () => requirements.filter((r) => r.confirmation_status === 'confirmed' && !r.superseded),
    [requirements],
  )

  async function pickDocument(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    const problem = documentProblem(file)
    if (problem) {
      setNotice(problem)
      return
    }
    setBusy(true)
    setNotice(null)
    const result = await service.uploadDocument(projectId, file)
    setBusy(false)
    if (result.state === 'error') {
      setNotice(`The document was not uploaded. ${result.error.message}`)
      return
    }
    const doc = result.data.document
    if (doc.extraction_status !== 'extracted') {
      setNotice(
        `“${doc.filename}” was stored but no text could be read: ${doc.extraction_error ?? 'unknown reason'}.`,
      )
    } else {
      setSelectedDocs((current) =>
        current.includes(doc.document_id) ? current : [...current, doc.document_id],
      )
      setNotice(
        result.data.duplicate ? `“${doc.filename}” was already uploaded; it is selected.` : null,
      )
    }
    void refresh()
  }

  async function submit() {
    if (busy || (statement.trim() === '' && selectedDocs.length === 0)) return
    setBusy(true)
    setNotice(null)
    const result = await service.submitIntent(projectId, {
      ...(statement.trim() ? { statement: statement.trim() } : {}),
      ...(selectedDocs.length ? { document_ids: selectedDocs } : {}),
      ...(runId ? { run_id: runId } : {}),
    })
    setBusy(false)
    if (result.state === 'error') {
      setNotice(`The expectations were not processed. ${result.error.message}`)
      return
    }
    const failed = result.data.intents.filter((i) => i.ai.error)
    setNotice(
      failed.length > 0
        ? 'The hosted AI was unavailable for part of this input. Your original text is saved; nothing was confirmed or invented.'
        : result.data.requirement_count === 0
          ? 'No verifiable requirement was found in that input.'
          : `${result.data.requirement_count} requirement(s) proposed. Review and confirm them below.`,
    )
    setStatement('')
    setSelectedDocs([])
    await refresh()
    onChanged?.()
  }

  async function decide(
    r: ProjectRequirement,
    action: 'confirm' | 'reject',
    overrides?: Record<string, unknown>,
  ) {
    setBusy(true)
    setNotice(null)
    const result =
      action === 'confirm'
        ? await service.confirmRequirement(projectId, r.requirement_id, overrides)
        : await service.rejectRequirement(projectId, r.requirement_id)
    setBusy(false)
    if (result.state === 'error') {
      setNotice(
        result.error.kind === 'conflict'
          ? 'That requirement cannot be confirmed yet: it needs a missing detail or contradicts another requirement.'
          : `The action failed. ${result.error.message}`,
      )
      return
    }
    await refresh()
    onChanged?.()
  }

  async function setCritical(r: ProjectRequirement, critical: boolean) {
    setBusy(true)
    setNotice(null)
    const result = await service.setCritical(projectId, r.requirement_id, critical)
    setBusy(false)
    if (result.state === 'error') {
      setNotice(`The safety rule setting was not saved. ${result.error.message}`)
      return
    }
    await refresh()
  }

  async function promote(verificationId: string) {
    setBusy(true)
    setNotice(null)
    const result = await service.promote(projectId, verificationId)
    setBusy(false)
    if (result.state === 'error') {
      setNotice(`The failure was not promoted. ${result.error.message}`)
      return
    }
    setVerifyResult((current) =>
      current && current.verification
        ? { ...current, verification: { ...current.verification, incident: result.data.incident } }
        : current,
    )
    await refresh()
  }

  async function verify() {
    if (busy || !verifyRunId) return
    setBusy(true)
    setNotice(null)
    setVerifyResult(null)
    const result = await service.verify(projectId, { run_id: verifyRunId })
    setBusy(false)
    if (result.state === 'error') {
      setNotice(
        result.error.kind === 'conflict'
          ? 'Nothing can be verified yet: confirm at least one requirement that applies to this run.'
          : `Verification did not run. ${result.error.message}`,
      )
      return
    }
    setVerifyResult(result.data)
    await refresh()
    onChanged?.()
  }

  const selectedRun = runs.find((r) => r.run_id === verifyRunId)
  const runIsActive = selectedRun ? ACTIVE_RUN.includes(selectedRun.status) : false
  const byVerification = useMemo(() => {
    const groups = new Map<string, ProjectVerificationRow[]>()
    for (const row of history)
      groups.set(row.verification_id, [...(groups.get(row.verification_id) ?? []), row])
    return [...groups.values()].reverse()
  }, [history])

  if (!loaded) {
    return (
      <section className="pw-card" aria-busy="true" role="status">
        <h2>Intent &amp; Verification</h2>
        <p className="pw-card__lead">Loading…</p>
      </section>
    )
  }

  return (
    <section className="pw" aria-label="Intent and verification">
      {loadError ? (
        <p className="pw-note" role="alert">
          Some project data could not be loaded. {loadError}
        </p>
      ) : null}
      {notice ? (
        <p className="pw-note" role="status">
          {notice}
        </p>
      ) : null}

      <div className="pw-grid">
        <div className="pw-card">
          <h2>Add expectations</h2>
          <p className="pw-card__lead">
            Describe what the agent should achieve, or upload a document. This works before, during
            and after training — it is the same interpretation and confirmation process each time.
          </p>
          <div className="pw-field">
            <label htmlFor="pw-statement">Expectations</label>
            <textarea
              id="pw-statement"
              className="pw-textarea"
              value={statement}
              maxLength={20000}
              disabled={busy}
              onChange={(e) => setStatement(e.target.value)}
              placeholder="e.g. The final episode reward must be at least 100."
            />
          </div>
          <div className="pw-field">
            <label htmlFor="pw-doc">Requirements document</label>
            <input
              id="pw-doc"
              type="file"
              accept={ACCEPTED_DOCUMENT_EXTENSIONS.join(',')}
              disabled={busy}
              onChange={(e) => void pickDocument(e)}
            />
            <span className="pw-muted">README, Markdown, TXT, PDF or DOCX, up to 2 MB.</span>
          </div>
          {documents.length > 0 ? (
            <ul className="pw-list" aria-label="Uploaded documents">
              {documents.map((d) => (
                <li key={d.document_id}>
                  <label className="pw-line">
                    <input
                      type="checkbox"
                      disabled={d.extraction_status !== 'extracted'}
                      checked={selectedDocs.includes(d.document_id)}
                      onChange={(e) =>
                        setSelectedDocs((cur) =>
                          e.target.checked
                            ? [...cur, d.document_id]
                            : cur.filter((x) => x !== d.document_id),
                        )
                      }
                    />
                    <span className="pw-text">{d.filename}</span>
                    <span className="pw-badge">
                      {d.extraction_status === 'extracted' ? `${d.text_chars} chars` : 'no text'}
                    </span>
                  </label>
                  {d.extraction_error ? (
                    <span className="pw-muted">{d.extraction_error}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
          <div className="pw-field" style={{ marginTop: 'var(--space-3)' }}>
            <label htmlFor="pw-run">Relates to run (optional)</label>
            <select
              id="pw-run"
              className="pw-select"
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
              disabled={busy}
            >
              <option value="">None — project level</option>
              {runs.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.run_id} ({r.status})
                </option>
              ))}
            </select>
          </div>
          <div className="pw-actions">
            <button
              type="button"
              className="pw-button pw-button--solid"
              disabled={busy || (statement.trim() === '' && selectedDocs.length === 0)}
              onClick={() => void submit()}
            >
              Interpret expectations
            </button>
            <span className="pw-badge">{STAGE_LABEL[stage]}</span>
          </div>
        </div>

        <div className="pw-card">
          <h2>Verify against a run</h2>
          <p className="pw-card__lead">
            Checks your confirmed requirements against the evidence recorded for one of this
            project&apos;s runs. The result comes from the deterministic engine, never from AI.
          </p>
          {runs.length === 0 ? (
            <p className="pw-note">
              No training run yet. Your requirements are saved with the project and will be
              available to verify as soon as a run exists.
            </p>
          ) : (
            <>
              <div className="pw-field">
                <label htmlFor="pw-verify-run">Run</label>
                <select
                  id="pw-verify-run"
                  className="pw-select"
                  value={verifyRunId}
                  onChange={(e) => {
                    setVerifyRunId(e.target.value)
                    setVerifyResult(null)
                  }}
                >
                  <option value="">Select a run…</option>
                  {runs.map((r) => (
                    <option key={r.run_id} value={r.run_id}>
                      {r.run_id} — {r.status}
                      {r.episode_count != null ? `, ${r.episode_count} episodes` : ''}
                    </option>
                  ))}
                </select>
              </div>
              {runIsActive ? (
                <p className="pw-note">
                  This run is still training. A result now is interim, based on the episodes
                  recorded so far; training is not affected.
                </p>
              ) : null}
              <div className="pw-actions">
                <button
                  type="button"
                  className="pw-button pw-button--solid"
                  disabled={busy || !verifyRunId || confirmed.length === 0}
                  onClick={() => void verify()}
                >
                  {runIsActive ? 'Verify progress so far' : 'Verify run'}
                </button>
                <span className="pw-muted">{confirmed.length} confirmed requirement(s)</span>
              </div>
            </>
          )}
          {verifyResult ? (
            <VerifyOutcome result={verifyResult} busy={busy} onPromote={(id) => void promote(id)} />
          ) : null}
        </div>
      </div>

      <div className="pw-card">
        <h2>Project requirements</h2>
        <p className="pw-card__lead">
          Saved for the project and kept across runs. A requirement is only authoritative once you
          confirm it.
        </p>
        {live.length === 0 ? (
          <p className="pw-note">No requirements yet. Add expectations above.</p>
        ) : (
          <ul className="pw-list" aria-label="Project requirements">
            {live.map((r) => (
              <RequirementRow
                key={r.requirement_id}
                requirement={r}
                busy={busy}
                onConfirm={(o) => void decide(r, 'confirm', o)}
                onReject={() => void decide(r, 'reject')}
                onCritical={(critical) => void setCritical(r, critical)}
              />
            ))}
          </ul>
        )}
      </div>

      <div className="pw-card">
        <h2>Verification history</h2>
        <p className="pw-card__lead">
          Every verification is kept and never rewritten; later changes create new records.
        </p>
        {byVerification.length === 0 ? (
          <p className="pw-note">No verification has been run for this project.</p>
        ) : (
          <ul className="pw-list" aria-label="Verification history">
            {byVerification.map((rows) => {
              const first = rows[0]
              return (
                <li key={first.verification_id}>
                  <div className="pw-line">
                    <span className="pw-text pw-mono">{first.run_id}</span>
                    <span className="pw-badge">
                      {first.stage === 'during_training'
                        ? 'During training (interim)'
                        : 'After training'}
                    </span>
                    <span className="pw-muted">{formatWhen(first.created_at)}</span>
                  </div>
                  <div className="pw-line">
                    {rows.map((row) => (
                      <span key={row.requirement_id} className="pw-badge pw-badge--strong">
                        {row.evaluation_status.toUpperCase()} · rev {row.requirement_revision}
                      </span>
                    ))}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </section>
  )
}

function VerifyOutcome({
  result,
  busy,
  onPromote,
}: {
  result: VerifyResult
  busy: boolean
  onPromote: (verificationId: string) => void
}) {
  if (result.state === 'waiting_for_evidence') {
    return (
      <p className="pw-note" role="status">
        Waiting for evidence. {result.reason} Nothing has been evaluated and no result was recorded.
      </p>
    )
  }
  const v = result.verification
  return (
    <div style={{ marginTop: 'var(--space-3)' }}>
      <p className="pw-section-label">
        {result.interim ? 'Interim result — run still training' : 'Completed result'}
      </p>
      {v ? (
        <>
          <div className="pw-line">
            <span className="pw-badge pw-badge--strong">
              Overall: {v.overall_status.toUpperCase()}
            </span>
            <span className="pw-muted pw-mono">{v.verification_id}</span>
          </div>
          <ul className="pw-list" aria-label="Requirement results">
            {(v.results ?? []).map((row) => (
              <li key={row.requirement_id}>
                <div className="pw-line">
                  <span className="pw-badge pw-badge--strong">{row.status.toUpperCase()}</span>
                  <span className="pw-text">{row.source_statement ?? row.description}</span>
                </div>
                <span className="pw-muted">
                  {row.evidence_refs?.length ?? 0} evidence reference(s)
                  {row.actual != null ? ` · observed ${JSON.stringify(row.actual)}` : ''}
                </span>
              </li>
            ))}
          </ul>
          {v.incident?.handoff_status === 'deferred_interim' ? (
            <div className="pw-note" role="status">
              Provisional result. The run is still training, so this failure was saved but no
              incident was created. It becomes an incident if you promote it, or automatically when
              a final verification of the finished run fails.{' '}
              <button
                type="button"
                className="pw-button"
                disabled={busy}
                onClick={() => onPromote(v.verification_id)}
              >
                Promote to incident
              </button>
            </div>
          ) : null}
          {v.incident?.incident_id ? (
            <p className="pw-note">
              {v.incident.handoff_status === 'created_interim'
                ? 'Incident raised from an interim result:'
                : 'Incident created:'}{' '}
              <Link
                to={`/diagnosis-recovery?incidentId=${encodeURIComponent(v.incident.incident_id)}`}
              >
                open the incident
              </Link>
            </p>
          ) : v.incident?.handoff_status === 'failed' ? (
            <p className="pw-note">
              The result is saved, but the incident handoff failed and can be retried.
            </p>
          ) : null}
        </>
      ) : null}
      {Object.keys(result.skipped).length > 0 ? (
        <p className="pw-note">
          {Object.keys(result.skipped).length} requirement(s) were not applied to this run (for
          example an environment version mismatch).
        </p>
      ) : null}
    </div>
  )
}
