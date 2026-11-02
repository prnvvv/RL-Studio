/**
 * Recovery service — LIVE Person 4 endpoints.
 *
 * Binds the mounted `recovery.p4_router` (`backend/api/routers/recovery.py`):
 * - `POST /api/v1/incidents/{incident_id}/recovery-assessments`      -> 201 RecoveryAssessment
 * - `GET  /api/v1/incidents/{incident_id}/recovery-assessments/{id}` -> RecoveryAssessment
 * - `POST /api/v1/incidents/{incident_id}/recoveries`               -> 201 Recovery
 * - `GET  /api/v1/incidents/{incident_id}/recoveries/{recovery_id}` -> Recovery
 *
 * Behavior rules mirrored from the backend (`root AGENTS.md` §13):
 * - Assessments are fail-closed server-side; the frontend only forwards the
 *   proposed strategy, checkpoint identity, and developer reason.
 * - Execution is only requested with `execute: true` AND the developer's
 *   `approval` — the backend still independently re-validates everything.
 * - POST requests carry an idempotency key so a retried submission cannot
 *   create a second recovery for the same intent.
 * - A `conflict` error (409) from the API means the recorded state disallows
 *   the transition; the UI must surface it as-is, not retry silently.
 */
import type {
  Recovery,
  RecoveryAssessment,
  RecoveryAssessmentRequest,
  RecoveryCreateRequest,
} from '../schemas/recovery'
import type { ServiceResult } from './types'
import { api } from './client'

export function recoveryAssessmentPath(incidentId: string): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}/recovery-assessments`
}

export function recoveryAssessmentItemPath(incidentId: string, assessmentId: string): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}/recovery-assessments/${encodeURIComponent(assessmentId)}`
}

export function recoveryPath(incidentId: string): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}/recoveries`
}

export function recoveryItemPath(incidentId: string, recoveryId: string): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}/recoveries/${encodeURIComponent(recoveryId)}`
}

export interface RecoveryService {
  createAssessment(
    incidentId: string,
    request: RecoveryAssessmentRequest,
  ): Promise<ServiceResult<RecoveryAssessment>>
  getAssessment(
    incidentId: string,
    assessmentId: string,
  ): Promise<ServiceResult<RecoveryAssessment>>
  createRecovery(
    incidentId: string,
    request: RecoveryCreateRequest,
  ): Promise<ServiceResult<Recovery>>
  getRecovery(incidentId: string, recoveryId: string): Promise<ServiceResult<Recovery>>
}

/** Real-mode adapter against the live recovery endpoints. */
const realAdapter: RecoveryService = {
  createAssessment(incidentId, request) {
    return api.post<RecoveryAssessment>(recoveryAssessmentPath(incidentId), { jsonBody: request })
  },
  getAssessment(incidentId, assessmentId) {
    return api.get<RecoveryAssessment>(recoveryAssessmentItemPath(incidentId, assessmentId))
  },
  createRecovery(incidentId, request) {
    return api.post<Recovery>(recoveryPath(incidentId), { jsonBody: request })
  },
  getRecovery(incidentId, recoveryId) {
    return api.get<Recovery>(recoveryItemPath(incidentId, recoveryId))
  },
}

/** Select the recovery adapter. Currently only the real adapter exists. */
export function createRecoveryService(): RecoveryService {
  return realAdapter
}
