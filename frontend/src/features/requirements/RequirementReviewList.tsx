import type {
  ExtractedRequirementDraft,
  IntentExtractionStatus,
  RequirementDecision,
  RequirementReviewState,
} from '../../schemas/intent'
import { RequirementCard } from './RequirementCard'

interface ReviewItem {
  draft: ExtractedRequirementDraft
  /** The review decision already recorded for this draft, if any. */
  decision?: RequirementDecision | null
}

interface RequirementReviewListProps {
  extractionStatus: IntentExtractionStatus
  warnings: string[]
  items: ReviewItem[]
  /** Called for the confirm/reject actions on still-undecided drafts. */
  onDecide: (draft: ExtractedRequirementDraft, decision: RequirementDecision) => void
  /** Decision request in flight, keyed by demo/backend requirement id. */
  pendingId: string | null
}

const STATUS_HEADINGS: Record<IntentExtractionStatus, string> = {
  accepted: 'Requirements extracted — review before confirming',
  ambiguous: 'Intent could not be parsed unambiguously',
  unsupported: 'Intent is outside the supported domain',
}

function reviewStateFor(item: ReviewItem): RequirementReviewState {
  if (item.decision === 'confirm') return 'confirmed'
  if (item.decision === 'reject') return 'rejected'
  return 'draft'
}

/**
 * Review panel for an extraction result.
 *
 * - Shows status honestly: ambiguous and unsupported statements are reported
 *   with the extraction warnings, never silently converted into drafts.
 * - Each draft is independent: a failed/duplicated decision disables only its
 *   own card (`pendingId`).
 * - No auto-confirmation: deciding is always an explicit action per card.
 */
export function RequirementReviewList({
  extractionStatus,
  warnings,
  items,
  onDecide,
  pendingId,
}: RequirementReviewListProps) {
  if (extractionStatus !== 'accepted') {
    return (
      <div
        role="status"
        style={{
          border: '1px dashed var(--border-primary)',
          borderRadius: 'var(--radius-md)',
          padding: 'var(--space-3)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
        }}
      >
        <span
          style={{
            fontSize: 'var(--text-sm)',
            color: 'var(--text-primary)',
            fontWeight: 600,
          }}
        >
          {STATUS_HEADINGS[extractionStatus]}
        </span>
        <ul
          style={{
            margin: 0,
            paddingLeft: '18px',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-1)',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <span
        role="status"
        style={{
          fontSize: 'var(--text-xs)',
          color: 'var(--text-secondary)',
          fontFamily: 'var(--font-sans)',
        }}
      >
        {STATUS_HEADINGS.accepted}
      </span>
      {items.length === 0 ? (
        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
          No requirements were extracted.
        </span>
      ) : (
        items.map((item) => {
          const decidedState = reviewStateFor(item)
          const pending = pendingId !== null && pendingId === item.draft.requirement_id
          const decided = item.decision === 'confirm' || item.decision === 'reject'
          return (
            <RequirementCard
              key={item.draft.requirement_id ?? item.draft.description}
              draft={item.draft}
              reviewState={decidedState}
              pending={pending}
              onConfirm={decided ? undefined : () => onDecide(item.draft, 'confirm')}
              onReject={decided ? undefined : () => onDecide(item.draft, 'reject')}
            />
          )
        })
      )}
      {items.some((item) => item.decision) && (
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          Decisions are recorded per plan; backend persistence is not yet wired.
        </span>
      )}
    </div>
  )
}
