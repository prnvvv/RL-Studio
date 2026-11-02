/**
 * Recovery contracts — LIVE Person 4 endpoints.
 *
 * Mirrors `backend/recovery/models.py` exactly as served by the mounted
 * `recovery.p4_router` (`backend/api/routers/recovery.py`):
 * - `POST /api/v1/incidents/{incident_id}/recovery-assessments`           -> 201 RecoveryAssessment
 * - `GET  /api/v1/incidents/{incident_id}/recovery-assessments/{id}`      -> RecoveryAssessment
 * - `POST /api/v1/incidents/{incident_id}/recoveries`                     -> 201 Recovery
 * - `GET  /api/v1/incidents/{incident_id}/recoveries/{recovery_id}`       -> Recovery
 *
 * Status semantics enforced by the backend and mirrored here
 * (`root AGENTS.md` §13, `frontend/AGENTS.md` §14.2):
 * - The assessment is fail-closed: `unknown` is a distinct eligibility, not
 *   eligibility. A blocked or unknown assessment must never gate an execution
 *   request through on the frontend.
 * - `proposed -> approved -> executing -> completed/failed` are distinct
 *   backend states; execution completing is not recovery success.
 * - The frontend presents and requests actions; all compatibility and
 *   restore validation is the backend's authority.
 */
import type { ISODateTime } from './shared'

/** Whether an incident may be recovered (`RecoveryEligibility`). */
export type RecoveryEligibility = 'eligible' | 'ineligible' | 'needs_review' | 'unknown'

/** Allow-listed recovery strategies (`RecoveryStrategy`). */
export type RecoveryStrategy =
  | 'restore_checkpoint'
  | 'correct_environment_config'
  | 'discard_pending_rollouts'
  | 'continue_with_fresh_experience'
  | 'evaluate_only'

/** Recovery lifecycle state (`RecoveryStatus`). */
export type RecoveryStatus =
  | 'proposed'
  | 'approved'
  | 'executing'
  | 'completed'
  | 'failed'
  | 'blocked'
  | 'cancelled'
  | 'evaluated'

/** Precondition / compatibility check outcome (`CheckOutcome`).
 * `pass` is serialized as "pass" by the backend enum alias. */
export type RecoveryCheckOutcome = 'pass' | 'fail' | 'unknown' | 'blocked' | 'skipped'

/** One named compatibility/precondition check (`CompatibilityCheck`). */
export interface RecoveryCompatibilityCheck {
  name: string
  outcome: RecoveryCheckOutcome
  detail: string
  evidence_ids: string[]
}

/** Approval mark carried on a recovery request (`Approval`). */
export interface RecoveryApproval {
  approved?: boolean
  approved_by?: string | null
  approved_at?: ISODateTime | null
  note?: string | null
}

/** Search body for a fail-closed compatibility assessment (`RecoveryAssessmentRequest`). */
export interface RecoveryAssessmentRequest {
  recovery_strategy?: RecoveryStrategy
  source_checkpoint_id?: string | null
  target_environment_version?: string | null
  target_agent_config_fingerprint?: string | null
  recovery_reason?: string | null
  discard_pending_rollouts?: boolean
  collect_fresh_experience?: boolean
  evidence_ids?: string[]
  details?: Record<string, unknown>
  /** Idempotency protection for retried assessment submissions. */
  idempotency_key?: string | null
}

/** Fail-closed recovery assessment (`RecoveryAssessment`). */
export interface RecoveryAssessment {
  recovery_assessment_id: string
  incident_id: string
  recovery_eligibility: RecoveryEligibility
  recovery_strategy: RecoveryStrategy
  recovery_reason: string | null
  source_checkpoint_id: string | null
  target_environment_version: string | null
  target_agent_config_fingerprint: string | null
  compatibility: RecoveryCompatibilityCheck[]
  lineage_gaps: string[]
  evidence_ids: string[]
  warnings: string[]
  errors: string[]
  details: Record<string, unknown>
  created_at: ISODateTime
}

/** One planned or executed step (`RecoveryAction`). */
export interface RecoveryAction {
  action: string
  status: string
  detail: string | null
  started_at: ISODateTime | null
  completed_at: ISODateTime | null
}

/** Execution-recovery request body (`RecoveryCreateRequest`). */
export interface RecoveryCreateRequest {
  assessment_id?: string | null
  recovery_strategy?: RecoveryStrategy | null
  source_checkpoint_id?: string | null
  target_environment_version?: string | null
  target_agent_config_fingerprint?: string | null
  recovery_reason?: string | null
  /** Whether the backend should execute; a proposal-only request uses false. */
  execute?: boolean
  approval?: RecoveryApproval | null
  discard_pending_rollouts?: boolean
  collect_fresh_experience?: boolean
  evidence_ids?: string[]
  details?: Record<string, unknown>
  /** Idempotency protection for retried recovery submissions. */
  idempotency_key?: string | null
}

/** The recovery record — plan and execution together (`Recovery`). */
export interface Recovery {
  recovery_id: string
  incident_id: string
  assessment_id: string | null
  recovery_status: RecoveryStatus
  recovery_strategy: RecoveryStrategy
  recovery_reason: string | null
  source_checkpoint_id: string | null
  recovery_artifact_id: string | null
  recovered_checkpoint_id: string | null
  target_environment_version: string | null
  target_agent_config_fingerprint: string | null
  recovery_started_at: ISODateTime | null
  recovery_completed_at: ISODateTime | null
  proposed_actions: RecoveryAction[]
  executed_actions: RecoveryAction[]
  preflight: Record<string, unknown>
  failure_reason: string | null
  evidence_ids: string[]
  warnings: string[]
  errors: string[]
  details: Record<string, unknown>
  created_at: ISODateTime
  updated_at: ISODateTime
}
