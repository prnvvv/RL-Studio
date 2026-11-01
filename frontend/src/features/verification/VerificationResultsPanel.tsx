import { StatusBadge } from '../../components/ui/StatusBadge'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingSkeleton } from '../../components/ui/LoadingSkeleton'
import { StaleDataNotice } from '../../components/ui/StaleDataNotice'
import { MOCK_DATA_LABEL, type MockData } from '../../mocks'
import type { EvidenceReference, VerificationResult } from '../../schemas/verification'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'
import type { ServiceError } from '../../services/types'
import { VerificationVerdictCard } from './VerificationVerdictCard'
import { EvidenceEventList } from './EvidenceEventList'

/** Query state whose payloads may be mock-wrapped (each carries its label). */
type PanelState<T> = ServiceQueryState<T | MockData<T>>

export interface VerificationResultsPanelProps {
  verification: PanelState<VerificationResult>
  evidence: PanelState<EvidenceReference[]>
  onOpenEvidence?: (evidenceRef: string) => void
  onReload?: () => void
}

/** Overall-status wording mapped for display, mirroring the check statuses. */
const OVERALL_LABELS: Record<VerificationResult['overall_status'], string> = {
  pass: 'Overall: passed',
  fail: 'Overall: failed',
  pending: 'Overall: pending',
  unknown: 'Overall: not evaluable',
  blocked: 'Overall: blocked',
  error: 'Overall: check errored',
}

/** Renders the loaded verification result, keeping the mock label attached. */
function LoadedVerification({
  verification,
  label,
  onOpenEvidence,
}: {
  verification: VerificationResult
  label?: string
  onOpenEvidence?: (evidenceRef: string) => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}
      >
        <StatusBadge
          label={OVERALL_LABELS[verification.overall_status]}
          tone={verification.overall_status === 'fail' ? 'strong' : 'neutral'}
          glyph={
            verification.overall_status === 'fail'
              ? 'cross'
              : verification.overall_status === 'pass'
                ? 'check'
                : 'query'
          }
        />
        {label && <StatusBadge label={label} tone="quiet" glyph="dot" />}
      </div>
      {verification.summary && (
        <p
          style={{
            margin: 0,
            fontSize: 'var(--text-sm)',
            color: 'var(--text-secondary)',
            lineHeight: 1.6,
          }}
        >
          {verification.summary}
        </p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        {verification.results.map((result) => (
          <VerificationVerdictCard
            key={result.requirement_id}
            result={result}
            onOpenEvidence={onOpenEvidence}
          />
        ))}
      </div>
      {verification.warnings.length > 0 && (
        <ul
          style={{
            margin: 0,
            paddingLeft: '18px',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-1)',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-secondary)',
          }}
        >
          {verification.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * Deterministic verification results panel.
 *
 * Every state the service can produce is rendered honestly: loading, request
 * failure (with retained data kept visible and marked stale), and loaded
 * results — with fixture-backed payloads visibly labelled as sample data.
 * The panel never synthesises verification outcomes.
 */
export function VerificationResultsPanel({
  verification,
  evidence,
  onOpenEvidence,
  onReload,
}: VerificationResultsPanelProps) {
  if (verification.state === 'loading') {
    return <LoadingSkeleton rows={4} />
  }

  if (verification.state === 'error') {
    if (verification.data !== null) {
      // Retained view: previously loaded data stays visible and marked stale.
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <StaleDataNotice subject="Verification results" />
          <ErrorState
            title="Verification could not be refreshed"
            description={verification.error.message}
          />
          <RetainedVerification
            verification={verification.data}
            onOpenEvidence={onOpenEvidence}
            evidence={evidence}
          />
        </div>
      )
    }

    return (
      <ErrorState
        title="Verification results are unavailable"
        description={verification.error.message}
        action={
          onReload ? (
            <button
              type="button"
              onClick={onReload}
              style={{
                padding: '6px 14px',
                background: 'var(--bg-input)',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-primary)',
                cursor: 'pointer',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Retry
            </button>
          ) : undefined
        }
      />
    )
  }

  return (
    <RetainedVerification
      verification={verification.data}
      onOpenEvidence={onOpenEvidence}
      evidence={evidence}
    />
  )
}

function RetainedVerification({
  verification,
  onOpenEvidence,
  evidence,
}: {
  verification: VerificationResult | MockData<VerificationResult>
  onOpenEvidence?: (evidenceRef: string) => void
  evidence: PanelState<EvidenceReference[]>
}) {
  const isLabeled = 'label' in verification

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <LoadedVerification
        verification={isLabeled ? verification.data : (verification as VerificationResult)}
        label={isLabeled ? MOCK_DATA_LABEL : undefined}
        onOpenEvidence={onOpenEvidence}
      />
      <EvidenceSection evidence={evidence} onOpenEvidence={onOpenEvidence} />
    </div>
  )
}

function EvidenceSection({
  evidence,
  onOpenEvidence,
}: {
  evidence: PanelState<EvidenceReference[]>
  onOpenEvidence?: (evidenceRef: string) => void
}) {
  if (evidence.state === 'loading') {
    return <LoadingSkeleton rows={2} />
  }

  if (evidence.state === 'error') {
    return (
      <p
        role="status"
        style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}
      >
        Evidence listing is not available right now: {describeEvidenceProblem(evidence.error)}
      </p>
    )
  }

  const payload = evidence.data
  const list = 'label' in payload ? payload.data : payload
  if (list.length === 0) {
    return (
      <p
        role="status"
        style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}
      >
        No evidence references have been recorded for this verification scope.
      </p>
    )
  }
  return <EvidenceEventList evidence={list} onOpenEvidence={onOpenEvidence} />
}

function describeEvidenceProblem(error: ServiceError): string {
  return error.message
}
