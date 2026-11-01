/**
 * Derivation of the honest investigation state for the panel header.
 *
 * Separate from the component file so the component module only exports
 * components (react-refresh/only-export-components). The state is derived
 * from what the service actually reported — never from what "should" have
 * happened: absent record stays `no_record`, provider outages stay
 * `provider_unavailable`, and any other failure stays `failed`.
 */
import type { InvestigationResult, InvestigationState } from '../../schemas/investigation'
import type { MockData } from '../../mocks'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'

export type InvestigationPanelState = ServiceQueryState<
  InvestigationResult | MockData<InvestigationResult>
>

export function investigateState(query: InvestigationPanelState): InvestigationState {
  if (query.state === 'ok') return 'completed'
  if (query.state === 'error') {
    if (query.error.kind === 'not_found' && query.data === null) return 'no_record'
    if (query.error.kind === 'unavailable' && query.data === null) return 'provider_unavailable'
    return 'failed'
  }
  return 'no_record'
}
