import type { CSSProperties } from 'react'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { formatCheckValue } from './checkValues'
import type { CheckStatus, VerificationCheckResult } from '../../schemas/verification'

interface VerificationVerdictCardProps {
  result: VerificationCheckResult
  /** Present when the parent can navigate to an evidence detail view. */
  onOpenEvidence?: (evidenceRef: string) => void
}

interface VerdictPresentation {
  label: string
  tone: 'neutral' | 'strong' | 'quiet'
  glyph: 'none' | 'check' | 'dot' | 'cross' | 'query'
}

/** Status mapping. `unknown`/`blocked` are never styled as a pass: a missing
 * expectation or blocked check is an inability to judge, not a success. */
const VERDICTS: Record<CheckStatus, VerdictPresentation> = {
  pass: { label: 'Passed', tone: 'neutral', glyph: 'check' },
  fail: { label: 'Failed', tone: 'strong', glyph: 'cross' },
  pending: { label: 'Check pending', tone: 'quiet', glyph: 'dot' },
  unknown: { label: 'Not evaluable', tone: 'quiet', glyph: 'query' },
  blocked: { label: 'Blocked', tone: 'quiet', glyph: 'query' },
  error: { label: 'Check errored', tone: 'quiet', glyph: 'cross' },
}

/** Unknown explanations come with the card, not as a guess. */
const UNKNOWN_EXPLANATIONS: Partial<Record<CheckStatus, string>> = {
  unknown: 'No applicable expectation is recorded for this requirement in the current scope, so no pass/fail claim is made.',
  blocked: 'The check could not run against the available evidence; no pass/fail claim is made.',
}

const row: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-2)',
  fontSize: 'var(--text-xs)',
  fontFamily: 'var(--font-sans)',
}

export function VerificationVerdictCard({ result, onOpenEvidence }: VerificationVerdictCardProps) {
  const verdict = VERDICTS[result.status]
  const unknownExplanation = UNKNOWN_EXPLANATIONS[result.status]

  return (
    <article
      data-testid={`verdict-${result.requirement_id}`}
      style={{
        border: '1px solid var(--border-secondary)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-3)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
        background: 'var(--bg-panel-raised)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
        <code style={{ fontSize: 'var(--text-xs)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
          {result.requirement_id}
        </code>
        <StatusBadge label={verdict.label} tone={verdict.tone} glyph={verdict.glyph} />
      </div>

      {unknownExplanation ? (
        <p style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
          {unknownExplanation}
        </p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
          <div style={row}>
            <span style={{ color: 'var(--text-secondary)', minWidth: '72px' }}>Expected</span>
            <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
              {formatCheckValue(result.expected)}
            </span>
          </div>
          <div style={row}>
            <span style={{ color: 'var(--text-secondary)', minWidth: '72px' }}>Observed</span>
            <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
              {formatCheckValue(result.actual)}
            </span>
          </div>
          {result.tolerance !== null && (
            <div style={row}>
              <span style={{ color: 'var(--text-secondary)', minWidth: '72px' }}>Tolerance</span>
              <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>±{result.tolerance}</span>
            </div>
          )}
        </div>
      )}

      <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center', flexWrap: 'wrap', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
        <span>{result.is_mandatory ? 'Mandatory check' : 'Advisory check'}</span>
        {result.evidence_refs.length > 0 && <span>{result.evidence_refs.length} evidence ref(s)</span>}
      </div>

      {result.evidence_refs.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
          {result.evidence_refs.map((ref) =>
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
      )}
    </article>
  )
}
