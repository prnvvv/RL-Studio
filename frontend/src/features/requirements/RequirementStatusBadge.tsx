import { StatusBadge } from '../../components/ui/StatusBadge'
import type { RequirementReviewState } from '../../schemas/intent'

interface RequirementStatusBadgeProps {
  state: RequirementReviewState
}

/**
 * Review-state presentation. A draft is only a draft until the recorded
 * backend state says otherwise — the label states that explicitly rather
 * than implying authorization or persistence.
 */
const LABELS: Record<RequirementReviewState, string> = {
  draft: 'Draft — awaiting review',
  confirmed: 'Confirmed for this session',
  rejected: 'Rejected',
}

export function RequirementStatusBadge({ state }: RequirementStatusBadgeProps) {
  return (
    <StatusBadge
      label={LABELS[state]}
      tone={state === 'confirmed' ? 'strong' : state === 'draft' ? 'neutral' : 'quiet'}
      glyph={state === 'confirmed' ? 'check' : state === 'rejected' ? 'cross' : 'query'}
    />
  )
}
