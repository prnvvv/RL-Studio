import { RequirementStatusBadge } from './RequirementStatusBadge'
import type { ExtractedRequirementDraft, RequirementReviewState } from '../../schemas/intent'

interface RequirementCardProps {
  draft: ExtractedRequirementDraft
  /** Current review state; defaults to the raw draft state. */
  reviewState?: RequirementReviewState
  /** Request in flight for this card's decision. */
  pending?: boolean
  onConfirm?: () => void
  onReject?: () => void
}

/** Authority wording, kept separate from the requirement's stated text. */
const SOURCE_LABELS: Record<ExtractedRequirementDraft['source'], string> = {
  developer_confirmed: 'Source: developer statement',
  test_derived: 'Source: derived from a test',
  code_inferred: 'Source: inferred from code — hypothesis',
}

/** Describe the rule without pretending to have validated it. */
function ruleSummary(
  ruleType: string | null,
  parameters: Record<string, unknown> | null,
): string | null {
  if (!ruleType) return null
  const paramText =
    parameters && Object.keys(parameters).length > 0
      ? ` (${Object.entries(parameters)
          .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
          .join(', ')})`
      : ''
  return `Rule: ${ruleType}${paramText}`
}

/**
 * One extracted requirement with its confirm/reject controls.
 *
 * The card never claims the requirement is live or enforced: until confirmed
 * and persisted by the backend it is a draft awaiting the developer's review
 * decision, and the badge plus source wording carry that distinction.
 */
export function RequirementCard({
  draft,
  reviewState = 'draft',
  pending = false,
  onConfirm,
  onReject,
}: RequirementCardProps) {
  const summary = ruleSummary(draft.rule_type, draft.parameters)

  return (
    <article
      aria-label={`Requirement review: ${draft.description}`}
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
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 'var(--space-3)',
        }}
      >
        <p
          style={{
            margin: 0,
            color: 'var(--text-primary)',
            fontSize: 'var(--text-sm)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          {draft.description}
        </p>
        <RequirementStatusBadge state={reviewState} />
      </div>
      {summary && (
        <span
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {summary}
        </span>
      )}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-3)',
          flexWrap: 'wrap',
          fontSize: 'var(--text-xs)',
          color: 'var(--text-secondary)',
        }}
      >
        <span>{SOURCE_LABELS[draft.source]}</span>
        {draft.environment_version && <span>Scope: {draft.environment_version}</span>}
      </div>
      {(onConfirm || onReject) && draft.requirement_id !== null && (
        <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-1)' }}>
          {onConfirm && (
            <button
              type="button"
              onClick={onConfirm}
              disabled={pending}
              style={{
                padding: '5px 12px',
                background: 'var(--bg-panel-raised)',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-primary)',
                fontWeight: 600,
                cursor: pending ? 'not-allowed' : 'pointer',
                fontFamily: 'var(--font-sans)',
                fontSize: 'var(--text-xs)',
              }}
            >
              Confirm
            </button>
          )}
          {onReject && (
            <button
              type="button"
              onClick={onReject}
              disabled={pending}
              style={{
                padding: '5px 12px',
                background: 'var(--bg-panel-raised)',
                border: '1px dashed var(--border-primary)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-secondary)',
                cursor: pending ? 'not-allowed' : 'pointer',
                fontFamily: 'var(--font-sans)',
                fontSize: 'var(--text-xs)',
              }}
            >
              Reject
            </button>
          )}
        </div>
      )}
    </article>
  )
}
