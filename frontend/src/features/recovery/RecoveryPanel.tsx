/**
 * Recovery assessment and controlled-recovery request panel (Person 4).
 *
 * Renders the recorded recovery assessment and any recovery record, and —
 * only when the recorded assessment opens the gate (`assessmentGate`) —
 * offers a confirmation-gated execution request sent to
 * `POST /api/v1/incidents/{incident_id}/recoveries` with `execute: true`,
 * the developer's approval mark, and an idempotency key.
 *
 * Hard rules (root AGENTS.md §13, frontend/AGENTS.md §14.2):
 * - The gate is display-level only; the backend remains the authority and
 *   re-validates compatibility, lineage, and eligibility itself.
 * - A closed gate renders an explicit reason and NO actionable control.
 * - Approval is never implied: it is recorded only through the confirmation
 *   dialog the developer explicitly confirmed.
 * - The idempotency key is generated once per intent and reused on retries of
 *   the same intent, so a repeated submission cannot create a second recovery.
 * - Completion is never presented as success; the outcome claim comes from
 *   `recoveryOutcomeClaim` and stays separate from any evaluation record.
 */
import { useCallback, useRef, useState } from 'react'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingSkeleton } from '../../components/ui/LoadingSkeleton'
import { ConfirmationDialog } from '../../components/ui/ConfirmationDialog'
import { unwrapMockData, type MockData } from '../../mocks'
import type { Recovery, RecoveryAssessment, RecoveryCreateRequest } from '../../schemas/recovery'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'
import type { ServiceError } from '../../services/types'
import type { RecoveryService } from '../../services/recovery'
import {
  assessmentGate,
  recoveryOutcomeClaim,
  recoveryPresentation,
  strategyLabel,
} from './recoveryGating'
import { createIdempotencyKey } from './idempotencyKey'

type PanelState<T> = ServiceQueryState<T | MockData<T>>

const detailText = {
  margin: 0,
  fontSize: 'var(--text-xs)',
  color: 'var(--text-secondary)',
  fontFamily: 'var(--font-sans)',
  lineHeight: 1.6,
} as const

const checkRow = {
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)',
  gap: 'var(--space-3)',
  alignItems: 'start',
  padding: 'var(--space-2) 0',
} as const

/** Request button style, shared with the app's inline secondary buttons. */
const requestButtonStyle = {
  padding: '6px 14px',
  background: 'var(--bg-input)',
  border: '1px solid var(--border-primary)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
  fontFamily: 'var(--font-sans)',
} as const

/** Outcome glyphs for compatibility checks; never colour-only signals. */
function checkGlyph(outcome: string): 'check' | 'cross' | 'query' {
  switch (outcome) {
    case 'pass':
      return 'check'
    case 'fail':
      return 'cross'
    default:
      return 'query'
  }
}

/** The assessment body: eligibility, identity, and the recorded check list. */
function AssessmentBody({
  assessment,
  onRequestExecution,
  requestPending,
}: {
  assessment: RecoveryAssessment
  onRequestExecution: () => void
  requestPending: boolean
}) {
  const gate = assessmentGate(assessment)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div
        style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', alignItems: 'center' }}
      >
        <StatusBadge
          label={`Eligibility: ${assessment.recovery_eligibility}`}
          tone={assessment.recovery_eligibility === 'eligible' ? 'neutral' : 'quiet'}
          glyph={assessment.recovery_eligibility === 'eligible' ? 'check' : 'query'}
        />
        <StatusBadge
          label={`Strategy: ${strategyLabel(assessment.recovery_strategy)}`}
          tone="neutral"
          glyph="dot"
        />
      </div>

      <p style={detailText}>
        {assessment.source_checkpoint_id
          ? `Source checkpoint: ${assessment.source_checkpoint_id}.`
          : 'No source checkpoint is recorded in the assessment.'}
        {assessment.target_environment_version
          ? ` Target environment: ${assessment.target_environment_version}.`
          : ''}
      </p>

      <section aria-label="Compatibility checks">
        <h4
          style={{
            margin: '0 0 var(--space-2) 0',
            fontSize: 'var(--text-xs)',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          Recorded compatibility checks ({assessment.compatibility.length})
        </h4>
        {assessment.compatibility.length === 0 ? (
          <p style={detailText}>
            The assessment records no compatibility checks. Absence of checks is not a pass, so
            nothing may be requested on the basis of this record.
          </p>
        ) : (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {assessment.compatibility.map((check, index) => (
              <li
                key={`${check.name}-${index}`}
                style={{
                  ...checkRow,
                  borderTop: index === 0 ? 'none' : '1px solid var(--border-secondary)',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
                  <span
                    style={{
                      fontSize: 'var(--text-sm)',
                      color: 'var(--text-primary)',
                      fontFamily: 'var(--font-sans)',
                    }}
                  >
                    {check.name}
                  </span>
                  <span
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--text-secondary)',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    {check.detail}
                  </span>
                </div>
                <div style={{ justifySelf: 'end' }}>
                  <StatusBadge
                    label={`Check: ${check.outcome}`}
                    tone={
                      check.outcome === 'pass'
                        ? 'neutral'
                        : check.outcome === 'fail'
                          ? 'strong'
                          : 'quiet'
                    }
                    glyph={checkGlyph(check.outcome)}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {assessment.lineage_gaps.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          {assessment.lineage_gaps.map((gap, index) => (
            <p key={index} style={detailText}>
              Lineage gap: {gap}
            </p>
          ))}
        </div>
      ) : null}

      {assessment.warnings.map((warning, index) => (
        <p key={`w-${index}`} style={detailText}>
          Warning: {warning}
        </p>
      ))}

      <div
        style={{
          borderTop: '1px solid var(--border-secondary)',
          paddingTop: 'var(--space-3)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
        }}
      >
        <p style={{ ...detailText, margin: 0 }} role="status">
          {gate.reason}
        </p>
        {gate.canRequestExecution ? (
          <div>
            <button
              type="button"
              style={requestButtonStyle}
              onClick={onRequestExecution}
              disabled={requestPending}
            >
              Request controlled recovery
            </button>
          </div>
        ) : null}
        <p style={detailText}>
          The backend re-validates compatibility, lineage, and eligibility itself; this request is a
          request, not authorisation to start work.
        </p>
      </div>
    </div>
  )
}

/** Any recorded recovery: lifecycle presentation, never a success claim. */
function RecoveryBody({ recovery }: { recovery: Recovery }) {
  const outcome = recoveryOutcomeClaim(recovery)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div
        style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', alignItems: 'center' }}
      >
        <StatusBadge
          label={`Recovery: ${recoveryPresentation(recovery.recovery_status)}`}
          tone={outcome.tone}
          glyph={recovery.recovery_status === 'completed' ? 'check' : 'query'}
        />
        <StatusBadge
          label={`Strategy: ${strategyLabel(recovery.recovery_strategy)}`}
          tone="neutral"
          glyph="dot"
        />
      </div>
      <p style={detailText}>{outcome.label}</p>

      {recovery.recovery_started_at ? (
        <p style={detailText}>Started: {recovery.recovery_started_at}</p>
      ) : null}
      {recovery.recovery_completed_at ? (
        <p style={detailText}>Completed: {recovery.recovery_completed_at}</p>
      ) : null}

      {/* Proposed and executed actions stay separate lists — never merged. */}
      {recovery.proposed_actions.length > 0 ? (
        <section aria-label="Proposed actions">
          <p style={{ ...detailText, fontWeight: 600 }}>Proposed actions</p>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {recovery.proposed_actions.map((action, index) => (
              <li key={index} style={{ ...detailText, padding: '2px 0' }}>
                {action.action} — {action.status}
                {action.detail ? ` (${action.detail})` : ''}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {recovery.executed_actions.length > 0 ? (
        <section aria-label="Executed actions">
          <p style={{ ...detailText, fontWeight: 600 }}>Executed actions</p>
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {recovery.executed_actions.map((action, index) => (
              <li key={index} style={{ ...detailText, padding: '2px 0' }}>
                {action.action} — {action.status}
                {action.detail ? ` (${action.detail})` : ''}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {recovery.failure_reason ? (
        <p style={{ ...detailText, fontWeight: 600 }}>Failure reason: {recovery.failure_reason}</p>
      ) : null}
    </div>
  )
}

export interface RecoveryPanelProps {
  incidentId: string
  service: RecoveryService
  assessment?: PanelState<RecoveryAssessment>
  recovery?: PanelState<Recovery>
  /** Reload the assessment read (a safe GET by the supplying page). */
  onReloadAssessment?: () => void
  /** Called with the created recovery record so the page can track it. */
  onRequested?: (recovery: Recovery) => void
}

export function RecoveryPanel({
  incidentId,
  service,
  assessment,
  recovery,
  onReloadAssessment,
  onRequested,
}: RecoveryPanelProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [requestPending, setRequestPending] = useState(false)
  const [requestError, setRequestError] = useState<ServiceError | null>(null)
  // One key per intent: created when the confirmation dialog opens, reused if
  // the developer retries the same request afterwards.
  const idempotencyRef = useRef<string | null>(null)

  const resolvedAssessment =
    assessment && assessment.state === 'ok' ? unwrapMockData(assessment.data) : null

  const gate = resolvedAssessment ? assessmentGate(resolvedAssessment) : null

  const openConfirm = useCallback(() => {
    idempotencyRef.current = createIdempotencyKey()
    setRequestError(null)
    setConfirmOpen(true)
  }, [])

  const closeConfirm = useCallback(() => {
    if (!requestPending) {
      setConfirmOpen(false)
    }
  }, [requestPending])

  const handleConfirm = useCallback(async () => {
    if (!resolvedAssessment || !idempotencyRef.current || requestPending) return
    setRequestPending(true)
    setRequestError(null)
    const request: RecoveryCreateRequest = {
      assessment_id: resolvedAssessment.recovery_assessment_id,
      execute: true,
      approval: {
        approved: true,
        approved_by: 'developer',
        approved_at: new Date().toISOString(),
        note: 'Requested from the recovery panel after explicit developer confirmation',
      },
      idempotency_key: idempotencyRef.current,
    }
    const result = await service.createRecovery(incidentId, request)
    setRequestPending(false)
    if (result.state === 'error') {
      // A conflict (409) or validation failure is surfaced verbatim; the
      // submission is never silently retried, and the key stays bound to the
      // same intent for any repeat the developer chooses to make.
      setRequestError(result.error)
      return
    }
    setConfirmOpen(false)
    onRequested?.(result.data)
  }, [resolvedAssessment, requestPending, service, incidentId, onRequested])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <section aria-label="Recovery assessment">
        {!assessment ? (
          <p style={detailText}>
            No assessment is supplied for this incident yet. Requesting a compatibility assessment
            is an explicit action; nothing is offered until the backend records one.
          </p>
        ) : assessment.state === 'loading' ? (
          <LoadingSkeleton rows={3} />
        ) : assessment.state === 'error' ? (
          <ErrorState
            title="The recovery assessment could not be loaded"
            description={assessment.error.message}
            action={
              onReloadAssessment ? (
                <button type="button" style={requestButtonStyle} onClick={onReloadAssessment}>
                  Retry
                </button>
              ) : undefined
            }
          />
        ) : (
          <AssessmentBody
            assessment={resolvedAssessment as RecoveryAssessment}
            onRequestExecution={openConfirm}
            requestPending={requestPending}
          />
        )}
      </section>

      {recovery ? (
        <section aria-label="Recovery record">
          <h4
            style={{
              margin: '0 0 var(--space-2) 0',
              fontSize: 'var(--text-xs)',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            Recorded recovery
          </h4>
          {recovery.state === 'loading' ? (
            <LoadingSkeleton rows={2} />
          ) : recovery.state === 'error' ? (
            <p role="status" style={detailText}>
              The recovery record could not be loaded: {recovery.error.message}
            </p>
          ) : (
            <RecoveryBody recovery={unwrapMockData(recovery.data)} />
          )}
        </section>
      ) : null}

      {/* The confirmation gate exists only for an open request; when the gate
          is closed there is no dialog and no actionable control. */}
      {gate?.canRequestExecution && resolvedAssessment && confirmOpen ? (
        <ConfirmationDialog
          title="Request controlled recovery"
          body={
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <p style={detailText}>
                The request will ask the backend to execute a controlled recovery for incident{' '}
                <span style={{ fontFamily: 'var(--font-mono)' }}>{incidentId}</span>, using the
                recorded assessment.
              </p>
              <p style={detailText}>
                Strategy: {strategyLabel(resolvedAssessment.recovery_strategy)}.{' '}
                {resolvedAssessment.source_checkpoint_id
                  ? `Source checkpoint: ${resolvedAssessment.source_checkpoint_id}.`
                  : 'No source checkpoint is recorded.'}
              </p>
              <p style={detailText}>
                The backend re-validates compatibility and lineage itself and may still block the
                operation. Execution completing is not a statement that recovery succeeded.
              </p>
            </div>
          }
          confirmLabel="Send execution request"
          destructive
          pending={requestPending}
          onConfirm={handleConfirm}
          onCancel={closeConfirm}
        />
      ) : null}

      {requestError ? (
        <p role="alert" style={detailText}>
          The recovery request could not be completed: {requestError.message}
        </p>
      ) : null}
    </div>
  )
}
