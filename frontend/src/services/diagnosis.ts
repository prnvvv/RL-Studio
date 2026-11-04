/**
 * Advisory diagnosis service. Binds `backend/api/routers/diagnosis.py` and `incidents.py`:
 *
 * - `GET  /api/v1/incidents?run_id=`                              incidents recorded for a run
 * - `POST /api/v1/incidents/{id}/investigations`                  evidence-grounded root-cause analysis (Muse Wonder)
 * - `GET  /api/v1/incidents/{id}/investigations`                  stored analyses, newest first
 * - `POST /api/v1/incidents/{id}/recovery-recommendations`        advisory options; never executed
 *
 * The model output is advisory: `confirmed` is always false and a recommendation is not an executed action.
 */
import type { ServiceResult } from './types'
import { api } from './client'

export interface IncidentListItem {
  incident_id: string
  run_id: string
  status: string
  severity: string | null
  summary: string | null
  requirement_id: string | null
  verification_id: string | null
  created_at: string
}

export interface Hypothesis {
  component: string
  description: string
  supporting_evidence_ids: string[]
  contradicting_evidence_ids: string[]
  confidence: number | null
  uncertainty: string | null
  kind: 'inference'
  evidence_support: string
}

export interface RootCauseResult {
  summary: string
  observed_facts: Array<{ statement: string; evidence_ids: string[]; kind: string }>
  hypotheses: Hypothesis[]
  root_cause_status: 'probable' | 'unresolved'
  confirmed: false
  missing_evidence: string[]
  recommended_investigation: string[]
  limitations: string[]
}

export interface RecoveryOption {
  action: string
  reason: string
  supporting_evidence_ids: string[]
  target_checkpoint_id: string | null
  expected_impact: string | null
  risks: string[]
  preconditions: string[]
  requires_user_authorization: boolean
  executor_supported?: boolean
  warnings?: string[]
}

export interface RecoveryRecommendationResult {
  summary: string
  options: RecoveryOption[]
  not_recommended: string[]
  missing_evidence: string[]
  limitations: string[]
}

export interface InvestigationRecord<T> {
  investigation_id: string
  incident_id: string
  run_id: string
  kind: 'root_cause' | 'recovery_plan'
  status: string
  created_at: string
  result: T
  ai: { model?: string; task?: string; fallback_used?: boolean; [key: string]: unknown }
  warnings: string[]
  reused?: boolean
}

export interface DiagnosisService {
  listIncidents(runId: string, signal?: AbortSignal): Promise<ServiceResult<IncidentListItem[]>>
  investigate(
    incidentId: string,
    force?: boolean,
  ): Promise<ServiceResult<InvestigationRecord<RootCauseResult>>>
  recommend(
    incidentId: string,
    force?: boolean,
  ): Promise<ServiceResult<InvestigationRecord<RecoveryRecommendationResult>>>
  listRecords(
    incidentId: string,
    signal?: AbortSignal,
  ): Promise<ServiceResult<Array<InvestigationRecord<unknown>>>>
}

const seg = encodeURIComponent
const SLOW_MS = 120_000

export function createDiagnosisService(): DiagnosisService {
  return {
    async listIncidents(runId, signal) {
      const result = await api.get<{ incidents: IncidentListItem[] }>(
        `/api/v1/incidents?run_id=${seg(runId)}`,
        { signal },
      )
      return result.state === 'ok' ? { state: 'ok', data: result.data.incidents } : result
    },
    investigate: (incidentId, force = false) =>
      api.post(`/api/v1/incidents/${seg(incidentId)}/investigations`, {
        jsonBody: { force },
        timeoutMs: SLOW_MS,
      }),
    recommend: (incidentId, force = false) =>
      api.post(`/api/v1/incidents/${seg(incidentId)}/recovery-recommendations`, {
        jsonBody: { force },
        timeoutMs: SLOW_MS,
      }),
    async listRecords(incidentId, signal) {
      const result = await api.get<{ investigations: Array<InvestigationRecord<unknown>> }>(
        `/api/v1/incidents/${seg(incidentId)}/investigations`,
        { signal },
      )
      return result.state === 'ok' ? { state: 'ok', data: result.data.investigations } : result
    },
  }
}
