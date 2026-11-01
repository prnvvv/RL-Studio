import { StatusBadge } from '../../components/ui/StatusBadge'
import type { InvestigationHypothesis } from '../../schemas/investigation'

interface HypothesisCardProps {
  hypothesis: InvestigationHypothesis
  /** Promote the styling for alternative explanations. */
  isAlternative?: boolean
  /** Present when the parent can navigate to an evidence detail view. */
  onOpenEvidence?: (evidenceRef: string) => void
}

/**
 * One model-proposed hypothesis (or alternative explanation).
 *
 * The card is deliberately loud about what the statement is NOT: a hypothesis
 * is never presented as a confirmed root cause, and a confidence number is
 * shown only when the record actually carries one, always labelled as an
 * unverified provider estimate rather than a calibrated probability.
 */
export function HypothesisCard({
  hypothesis,
  isAlternative = false,
  onOpenEvidence,
}: HypothesisCardProps) {
  const evidenceRefs =
    hypothesis.supporting_evidence_refs.length > 0 ? hypothesis.supporting_evidence_refs : []

  return (
    <article
      data-testid={`hypothesis-${hypothesis.hypothesis_id}`}
      style={{
        border: isAlternative
          ? '1px dashed var(--border-primary)'
          : '1px solid var(--border-secondary)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-3)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
        background: 'var(--bg-panel-raised)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 'var(--space-3)',
        }}
      >
        <StatusBadge
          label={isAlternative ? 'Alternative explanation' : 'Hypothesis'}
          tone={isAlternative ? 'quiet' : 'strong'}
          glyph="query"
        />
        {hypothesis.confidence !== null && (
          <span
            style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--text-muted)',
              fontFamily: 'var(--font-sans)',
              whiteSpace: 'nowrap',
            }}
          >
            {`Confidence (provider estimate, unverified): ${hypothesis.confidence}`}
          </span>
        )}
      </div>
      <p
        style={{
          margin: 0,
          fontSize: 'var(--text-sm)',
          color: 'var(--text-primary)',
          lineHeight: 1.6,
        }}
      >
        {hypothesis.statement}
      </p>
      {hypothesis.reasoning && (
        <p
          style={{
            margin: 0,
            fontSize: 'var(--text-xs)',
            color: 'var(--text-secondary)',
            lineHeight: 1.6,
          }}
        >
          {hypothesis.reasoning}
        </p>
      )}
      {evidenceRefs.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
          {evidenceRefs.map((ref) =>
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
      {hypothesis.confidence !== null && (
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
          A hypothesis is a proposed explanation only; it does not establish cause and cannot
          authorise any recovery action.
        </span>
      )}
    </article>
  )
}
