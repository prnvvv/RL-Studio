import { StatusBadge } from '../../components/ui/StatusBadge'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { StaleDataNotice } from '../../components/ui/StaleDataNotice'
import { ExpandableSection } from '../../components/ui/ExpandableSection'
import { LoadingSkeleton } from '../../components/ui/LoadingSkeleton'
import { MOCK_DATA_LABEL, type MockData } from '../../mocks'
import type { InvestigationResult } from '../../schemas/investigation'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'
import { ProviderStatusBadge } from './ProviderStatusBadge'
import { HypothesisCard } from './HypothesisCard'
import { investigateState } from './investigationState'

type PanelState<T> = ServiceQueryState<T | MockData<T>>

export interface InvestigationPanelProps {
  incidentId: string | null
  investigation: PanelState<InvestigationResult>
  onRequest?: () => void
  requestPending?: boolean
  onOpenEvidence?: (evidenceId: string) => void
}

const listStyle = {
  margin: 0,
  paddingLeft: '18px',
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-1)',
  fontSize: 'var(--text-xs)',
  color: 'var(--text-secondary)',
  fontFamily: 'var(--font-sans)',
} as const

const listRowStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-2)',
  fontSize: 'var(--text-xs)',
  fontFamily: 'var(--font-sans)',
} as const

function EvidenceChips({
  refs,
  onOpenEvidence,
}: {
  refs: string[]
  onOpenEvidence?: (id: string) => void
}) {
  if (refs.length === 0) return null
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
      {refs.map((ref) =>
        onOpenEvidence ? (
          <button
            key={ref}
            type="button"
            onClick={() => onOpenEvidence(ref)}
            style={{
              padding: '2px 8px',
              background: 'transparent',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-primary)',
              cursor: 'pointer',
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
            }}
          >
            {ref}
          </button>
        ) : (
          <code
            key={ref}
            style={{
              padding: '2px 8px',
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
              color: 'var(--text-secondary)',
              border: '1px dashed var(--border-secondary)',
              borderRadius: 'var(--radius-sm)',
            }}
          >
            {ref}
          </code>
        ),
      )}
    </div>
  )
}

function LoadedInvestigation({
  investigation,
  label,
  onOpenEvidence,
}: {
  investigation: InvestigationResult
  label?: string
  onOpenEvidence?: (id: string) => void
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}
      >
        {label && <StatusBadge label={label} tone="quiet" glyph="dot" />}
      </div>

      {investigation.summary && (
        <p
          style={{
            margin: 0,
            fontSize: 'var(--text-sm)',
            color: 'var(--text-primary)',
            lineHeight: 1.6,
          }}
        >
          {investigation.summary}
        </p>
      )}

      {investigation.facts.length === 0 ? (
        <span role="status" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          No observed facts were recorded for this investigation.
        </span>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            Observed facts
          </span>
          {investigation.facts.map((fact) => (
            <div
              key={fact.statement}
              style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}
            >
              <p style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--text-primary)' }}>
                {fact.statement}
              </p>
              <EvidenceChips refs={fact.evidence_refs} onOpenEvidence={onOpenEvidence} />
            </div>
          ))}
        </div>
      )}

      {investigation.hypotheses.length === 0 ? (
        <span role="status" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          The provider returned no hypotheses; no cause claim is implied.
        </span>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            Proposed hypotheses
          </span>
          {investigation.hypotheses.map((hypothesis) => (
            <HypothesisCard
              key={hypothesis.hypothesis_id}
              hypothesis={hypothesis}
              onOpenEvidence={onOpenEvidence}
            />
          ))}
        </div>
      )}

      {investigation.alternatives.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            Alternative explanations
          </span>
          {investigation.alternatives.map((hypothesis) => (
            <HypothesisCard
              key={hypothesis.hypothesis_id}
              hypothesis={hypothesis}
              isAlternative
              onOpenEvidence={onOpenEvidence}
            />
          ))}
        </div>
      )}

      {investigation.contradictions.length > 0 && (
        <ExpandableSection
          title="Contradictions"
          summary={`${investigation.contradictions.length} recorded`}
        >
          <ul style={listStyle}>
            {investigation.contradictions.map((contradiction) => (
              <li key={contradiction}>{contradiction}</li>
            ))}
          </ul>
        </ExpandableSection>
      )}

      {investigation.recommended_tests.length > 0 && (
        <ExpandableSection
          title="Recommended diagnostic tests"
          summary={`${investigation.recommended_tests.length} suggested`}
        >
          <ul style={listStyle}>
            {investigation.recommended_tests.map((test) => (
              <li key={test}>{test}</li>
            ))}
          </ul>
        </ExpandableSection>
      )}

      {investigation.suggested_action && (
        <div
          style={{
            border: '1px dashed var(--border-primary)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-3)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-2)',
          }}
        >
          <div
            style={{
              display: 'flex',
              gap: 'var(--space-2)',
              alignItems: 'center',
              flexWrap: 'wrap',
            }}
          >
            <StatusBadge label="Suggested action — not executed" tone="quiet" glyph="dot" />
            {investigation.suggested_action.requires_confirmation && (
              <StatusBadge label="Requires confirmation" tone="neutral" glyph="query" />
            )}
          </div>
          <p
            style={{
              margin: 0,
              fontSize: 'var(--text-xs)',
              color: 'var(--text-primary)',
              lineHeight: 1.6,
            }}
          >
            {investigation.suggested_action.description}
          </p>
          {investigation.suggested_action.target && (
            <code
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 'var(--text-xs)',
                color: 'var(--text-secondary)',
              }}
            >
              Target: {investigation.suggested_action.target}
            </code>
          )}
        </div>
      )}

      <ExpandableSection
        title="Missing evidence"
        summary={`${investigation.missing_evidence.length} gap(s)`}
      >
        {investigation.missing_evidence.length === 0 ? (
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
            No evidence gaps were recorded.
          </span>
        ) : (
          <ul style={listStyle}>
            {investigation.missing_evidence.map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        )}
      </ExpandableSection>

      <ExpandableSection
        title="Limitations"
        summary={`${investigation.limitations.length} recorded`}
      >
        <ul style={listStyle}>
          {investigation.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </ExpandableSection>

      {investigation.provider && (
        <ExpandableSection title="Analysis details" summary="Provider metadata">
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-1)',
              fontSize: 'var(--text-xs)',
              color: 'var(--text-secondary)',
            }}
          >
            <span style={listRowStyle}>
              Provider provider:{' '}
              <code style={{ fontFamily: 'var(--font-mono)' }}>
                {investigation.provider.provider}
              </code>
            </span>
            <span style={listRowStyle}>
              Model:{' '}
              <code style={{ fontFamily: 'var(--font-mono)' }}>
                {investigation.provider.model ?? 'not recorded'}
              </code>
            </span>
            {investigation.provider.prompt_version && (
              <span style={listRowStyle}>
                Prompt version: {investigation.provider.prompt_version}
              </span>
            )}
          </div>
        </ExpandableSection>
      )}
    </div>
  )
}

/**
 * AI investigation panel.
 *
 * Renders only what the endpoint actually returned. "No investigation
 * recorded" is distinct from "provider unavailable", and both are distinct
 * from a completed analysis. Requesting an investigation is always an
 * explicit, disableable action; nothing here can authorise a recovery step.
 */
export function InvestigationPanel({
  incidentId,
  investigation,
  onRequest,
  requestPending = false,
  onOpenEvidence,
}: InvestigationPanelProps) {
  const state = investigateState(investigation)

  if (investigation.state === 'loading') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        <ProviderStatusBadge state="no_record" />
        <LoadingSkeleton rows={4} />
      </div>
    )
  }

  if (investigation.state === 'error') {
    const canRequest = onRequest !== undefined && incidentId !== null && state === 'no_record'
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <ProviderStatusBadge state={state} />
        </div>
        {investigation.data !== null ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <StaleDataNotice subject="Investigation findings" />
            <ErrorState
              title="Investigation could not be refreshed"
              description={investigation.error.message}
            />
            <LoadedInvestigation
              investigation={
                'label' in investigation.data
                  ? investigation.data.data
                  : (investigation.data as InvestigationResult)
              }
              label={'label' in investigation.data ? MOCK_DATA_LABEL : undefined}
              onOpenEvidence={onOpenEvidence}
            />
          </div>
        ) : state === 'no_record' ? (
          <EmptyState
            title="No investigation has been run"
            description={
              incidentId
                ? 'Requesting an investigation is an explicit action. The backend analyses the recorded evidence for the focused incident and returns hypotheses separately from deterministic results.'
                : 'Focus an incident to make investigation available.'
            }
            action={
              canRequest ? (
                <button
                  type="button"
                  onClick={onRequest}
                  disabled={requestPending}
                  aria-busy={requestPending || undefined}
                  style={{
                    padding: '6px 14px',
                    background: 'var(--text-primary)',
                    color: 'var(--bg-primary)',
                    border: 'none',
                    borderRadius: 'var(--radius-sm)',
                    cursor: requestPending ? 'not-allowed' : 'pointer',
                    opacity: requestPending ? 0.6 : 1,
                    fontFamily: 'var(--font-sans)',
                    fontSize: 'var(--text-sm)',
                  }}
                >
                  {requestPending ? 'Requesting investigation…' : 'Request investigation'}
                </button>
              ) : undefined
            }
          />
        ) : (
          <ErrorState
            title="The investigation could not be loaded"
            description={investigation.error.message}
          />
        )}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <ProviderStatusBadge state="completed" />
      <LoadedInvestigation
        investigation={
          'label' in investigation.data
            ? investigation.data.data
            : (investigation.data as InvestigationResult)
        }
        label={'label' in investigation.data ? MOCK_DATA_LABEL : undefined}
        onOpenEvidence={onOpenEvidence}
      />
    </div>
  )
}
