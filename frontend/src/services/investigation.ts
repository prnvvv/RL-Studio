/**
 * Investigation (AI diagnosis) service (@planned contract).
 *
 * The diagnosis router is not mounted in `backend/api/app.py` and Person 3's
 * investigation endpoints do not exist, so real mode calls the planned paths
 * below and callers receive honest `not_found` / `unavailable` results until
 * they exist. With `VITE_USE_MOCKS=true`, fixtures from
 * `src/mocks/investigation.ts` are returned wrapped in `MockData`; a demo
 * investigation exists only after an explicit request, mirroring the honest
 * "no analysis has run yet" state.
 */
import type { InvestigationResult } from '../schemas/investigation'
import type { MockData } from '../mocks/index'
import type { ServiceResult } from './types'
import { api, recordNotFound } from './client'
import { labeledMockData, mocksEnabled } from '../mocks/index'
import { mockInvestigationAdapter } from '../mocks/investigation'

type WithMock<T> = T | MockData<T>

/** @planned investigation record lookup / request for an incident. */
export function investigationPath(incidentId: string): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}/investigation`
}

export interface InvestigationService {
  getInvestigation(incidentId: string): Promise<ServiceResult<WithMock<InvestigationResult>>>
  /**
   * Ask the backend investigator to analyse an incident's evidence. Real
   * mode POSTs the planned path; mock mode records the demo fixture. This is
   * always an explicit user action — nothing requests analysis implicitly.
   */
  requestInvestigation(incidentId: string): Promise<ServiceResult<WithMock<InvestigationResult>>>
}

/** Real-mode calls against the planned endpoint; honest errors until it exists. */
const realAdapter: InvestigationService = {
  getInvestigation(incidentId) {
    return api.get<InvestigationResult>(investigationPath(incidentId))
  },
  requestInvestigation(incidentId) {
    return api.post<InvestigationResult>(investigationPath(incidentId))
  },
}

/** Mock-mode adapter; not-run-yet stays not_found rather than fabricating analysis. */
const mockedAdapter: InvestigationService = {
  async getInvestigation(incidentId) {
    const outcome = await mockInvestigationAdapter.getInvestigation(incidentId)
    return outcome === null ? recordNotFound() : { state: 'ok', data: labeledMockData(outcome) }
  },
  async requestInvestigation(incidentId) {
    try {
      const outcome = await mockInvestigationAdapter.requestInvestigation(incidentId)
      return { state: 'ok', data: labeledMockData(outcome) }
    } catch {
      // Unknown incident ids carry no demo fixture: report absence honestly.
      return recordNotFound()
    }
  },
}

/** Select the adapter from the mock opt-in flag. */
export function createInvestigationService(): InvestigationService {
  return mocksEnabled() ? mockedAdapter : realAdapter
}
