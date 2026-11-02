/**
 * Evaluation service — LIVE Person 4 endpoints.
 *
 * Binds the mounted `evaluation.p4_router` (`backend/api/routers/evaluation.py`):
 * - `POST /api/v1/incidents/{incident_id}/evaluations`           -> 201 Evaluation
 * - `GET  /api/v1/incidents/{incident_id}/evaluations/{eval_id}` -> Evaluation
 *
 * Behavior rules mirrored from the backend:
 * - The frontend composes the episode records supplied by the backend/config
 *   context; it never authors rewards, successes, or baseline identities.
 * - Acceptance is computed server-side (`recovery_verification_status`,
 *   `recovery_verified`); the frontend displays those fields verbatim.
 * - POST requests carry an idempotency key so retried submissions cannot
 *   create duplicate evaluations for the same recovery.
 */
import type { Evaluation, EvaluationCreateRequest } from '../schemas/evaluation'
import type { ServiceResult } from './types'
import { api } from './client'

export function evaluationPath(incidentId: string): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}/evaluations`
}

export function evaluationItemPath(incidentId: string, evaluationId: string): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}/evaluations/${encodeURIComponent(evaluationId)}`
}

export interface EvaluationService {
  createEvaluation(
    incidentId: string,
    request: EvaluationCreateRequest,
  ): Promise<ServiceResult<Evaluation>>
  getEvaluation(incidentId: string, evaluationId: string): Promise<ServiceResult<Evaluation>>
}

/** Real-mode adapter against the live evaluation endpoints. */
const realAdapter: EvaluationService = {
  createEvaluation(incidentId, request) {
    return api.post<Evaluation>(evaluationPath(incidentId), { jsonBody: request })
  },
  getEvaluation(incidentId, evaluationId) {
    return api.get<Evaluation>(evaluationItemPath(incidentId, evaluationId))
  },
}

/** Select the evaluation adapter. Currently only the real adapter exists. */
export function createEvaluationService(): EvaluationService {
  return realAdapter
}
