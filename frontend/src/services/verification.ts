/**
 * Verification & incident service (@planned contract).
 *
 * The Person 3 incident/verification endpoints do not exist yet (the
 * diagnosis router is not mounted in `backend/api/app.py`), so real mode
 * issues calls against the documented planned paths below and callers
 * receive honest `not_found` / `unavailable` errors until they exist
 * (frontend/AGENTS.md §16.2). With `VITE_USE_MOCKS=true`, mock fixtures from
 * `src/mocks/verification.ts` are returned wrapped in `MockData` (the shared
 * `Sample data` label travels with them); unknown incident ids stay honest
 * `not_found` even in mock mode — fixtures never pretend arbitrary incidents
 * exist.
 */
import type { AnomalyObservation, EvidenceReference, IncidentRecord, VerificationResult } from '../schemas/verification'
import type { MockData } from '../mocks/index'
import type { ServiceResult } from './types'
import { api, recordNotFound } from './client'
import { labeledMockData, mocksEnabled } from '../mocks/index'
import { mockVerificationAdapter } from '../mocks/verification'

/** @planned incident record lookup. */
export function incidentPath(incidentId: string): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}`
}
/** @planned deterministic verification results for an incident. */
export function incidentVerificationPath(incidentId: string): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}/verification`
}
/** @planned evidence references collected for an incident. */
export function incidentEvidencePath(incidentId: string): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}/evidence`
}
/** @planned anomaly observations in scope for an incident. */
export function incidentAnomaliesPath(incidentId: string): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}/anomalies`
}

type WithMock<T> = T | MockData<T>

export interface VerificationService {
  getIncident(incidentId: string): Promise<ServiceResult<WithMock<IncidentRecord>>>
  getVerificationResult(incidentId: string): Promise<ServiceResult<WithMock<VerificationResult>>>
  listEvidence(incidentId: string): Promise<ServiceResult<WithMock<EvidenceReference[]>>>
  listAnomalies(incidentId: string): Promise<ServiceResult<WithMock<AnomalyObservation[]>>>
}

/** Real-mode calls against the planned endpoints; honest errors until they exist. */
const realAdapter: VerificationService = {
  getIncident(incidentId) {
    return api.get<IncidentRecord>(incidentPath(incidentId))
  },
  getVerificationResult(incidentId) {
    return api.get<VerificationResult>(incidentVerificationPath(incidentId))
  },
  listEvidence(incidentId) {
    return api.get<EvidenceReference[]>(incidentEvidencePath(incidentId))
  },
  listAnomalies(incidentId) {
    return api.get<AnomalyObservation[]>(incidentAnomaliesPath(incidentId))
  },
}

/** Mock-mode adapter: labeled payloads, unknown ids map to stable not_found. */
const mockedAdapter: VerificationService = {
  async getIncident(incidentId) {
    const outcome = await mockVerificationAdapter.getIncident(incidentId)
    return outcome === null ? recordNotFound() : { state: 'ok', data: labeledMockData(outcome) }
  },
  async getVerificationResult(incidentId) {
    const outcome = await mockVerificationAdapter.getVerificationResult(incidentId)
    return outcome === null ? recordNotFound() : { state: 'ok', data: labeledMockData(outcome) }
  },
  async listEvidence(incidentId) {
    const outcome = await mockVerificationAdapter.listEvidence(incidentId)
    return { state: 'ok', data: labeledMockData(outcome) }
  },
  async listAnomalies(incidentId) {
    const outcome = await mockVerificationAdapter.listAnomalies(incidentId)
    return { state: 'ok', data: labeledMockData(outcome) }
  },
}

/** Select the adapter from the mock opt-in flag. */
export function createVerificationService(): VerificationService {
  return mocksEnabled() ? mockedAdapter : realAdapter
}
