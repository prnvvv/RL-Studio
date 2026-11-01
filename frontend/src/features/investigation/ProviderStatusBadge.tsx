import { StatusBadge } from '../../components/ui/StatusBadge'
import type { InvestigationState } from '../../schemas/investigation'

interface ProviderStatusBadgeProps {
  state: InvestigationState
}

/**
 * Investigation-provider presentation. Each state is a claim about what
 * actually happened (or did not happen) — the labels never imply that the
 * model produced a validated root cause, and `no_record` never implies an
 * investigation ran and failed.
 */
const LABELS: Record<InvestigationState, { label: string; tone: 'neutral' | 'strong' | 'quiet'; glyph: 'none' | 'check' | 'dot' | 'cross' | 'query' }> = {
  no_record: { label: 'No investigation recorded', tone: 'quiet', glyph: 'none' },
  completed: { label: 'Investigation completed', tone: 'neutral', glyph: 'check' },
  provider_unavailable: { label: 'Provider unavailable', tone: 'quiet', glyph: 'cross' },
  failed: { label: 'Investigation failed', tone: 'strong', glyph: 'cross' },
}

export function ProviderStatusBadge({ state }: ProviderStatusBadgeProps) {
  const presentation = LABELS[state]
  return (
    <StatusBadge label={presentation.label} tone={presentation.tone} glyph={presentation.glyph} />
  )
}
