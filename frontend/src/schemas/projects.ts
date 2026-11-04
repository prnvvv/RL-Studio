/**
 * Project management contracts, mirroring `backend/api/routers/projects.py`.
 *
 * Requirement lifecycle, validation and verification statuses are the Phase 3 values unchanged: this module adds
 * no result semantics of its own.
 */

export type TrainingState = 'not_started' | 'active' | 'completed'

export type ProjectStage = 'pre_training' | 'during_training' | 'post_training' | 'project_level'

export interface ProjectSummary {
  project_id: string
  name: string
  description: string | null
  status: string
  created_at: string
  updated_at: string
  agent: Record<string, unknown>
  environment: Record<string, unknown>
  training: {
    state: TrainingState
    run_count: number
    active_runs: number
    completed_runs: number
  }
  requirements: { total: number; confirmed: number; pending: number }
  last_verification: { run_id: string; status: string; at: string } | null
  verification_count: number
  document_count?: number
}

export interface ProjectCreateRequest {
  name: string
  description?: string
  agent?: Record<string, unknown>
  environment?: Record<string, unknown>
  intent?: { statement?: string; document_ids?: string[] }
}

export interface ProjectUpdateRequest {
  name?: string
  description?: string | null
  agent?: Record<string, unknown>
  environment?: Record<string, unknown>
}

export interface ProjectDocument {
  document_id: string
  project_id: string
  filename: string
  content_type: string
  size_bytes: number
  sha256: string
  extraction_status: 'extracted' | 'failed'
  extraction_error: string | null
  text_chars: number
  preview: string | null
  created_at: string
}

export interface DocumentUploadResult {
  document: ProjectDocument
  duplicate: boolean
}

export type RequirementLifecycle =
  | 'draft'
  | 'needs_clarification'
  | 'confirmed'
  | 'rejected'
  | 'invalid'
  | 'verified'
  | 'failed'
  | 'unknown'

export interface ProjectRequirement {
  requirement_id: string
  project_id: string | null
  requirement_key: string
  requirement_revision: number
  supersedes: string | null
  superseded: boolean
  stage: ProjectStage | null
  source: { type?: string; filename?: string; document_id?: string }
  category: string
  source_statement: string
  description: string
  comparison_operator: string | null
  expected_value: unknown
  tolerance: number | null
  lifecycle_status: RequirementLifecycle
  validation_status: string
  confirmation_status: 'proposed' | 'confirmed' | 'rejected'
  clarification_question: string | null
  validation: { reasons?: string[]; warnings?: string[] }
  awaiting_run_evidence: boolean
  conflicts_with: string[]
  latest_verification?: {
    verification_id: string
    run_id: string
    status: string
    stage: string
    at: string
  } | null
}

export interface ProjectIntent {
  intent_id: string
  status: string
  status_reason: string | null
  original_text: string
  stage: ProjectStage | null
  source: { type?: string; filename?: string; document_id?: string }
  requirements: ProjectRequirement[]
  ai: { error?: { code: string; message: string } | null; origin?: string | null }
}

export interface IntentSubmitRequest {
  statement?: string
  document_ids?: string[]
  run_id?: string
  supersedes?: string
}

export interface IntentSubmitResult {
  project_id: string
  stage: ProjectStage
  run_id: string | null
  intents: ProjectIntent[]
  requirement_count: number
}

export interface ProjectRun {
  run_id: string
  project_id: string
  status: string
  environment_id: string | null
  environment_version: string | null
  agent: string | null
  name: string | null
  episode_count: number | null
  step_count: number | null
  created_at: string
  finished_at: string | null
}

export interface VerificationResultRow {
  requirement_id: string
  status: string
  description?: string | null
  source_statement?: string | null
  evidence_refs?: string[]
  expected?: unknown
  actual?: unknown
}

export interface RunVerificationView {
  verification_id: string
  run_id: string
  overall_status: string
  results?: VerificationResultRow[]
  incident: {
    handoff_status: string
    incident_id: string | null
    error_code: string | null
  } | null
  created_at: string
}

export interface VerifyResult {
  project_id: string
  run_id: string
  state: 'evaluated' | 'waiting_for_evidence'
  stage: ProjectStage
  interim?: boolean
  reason?: string
  evaluation_window: Record<string, unknown>
  verification: RunVerificationView | null
  skipped: Record<string, string>
}

export interface ProjectVerificationRow {
  project_id: string
  run_id: string
  verification_id: string
  requirement_id: string
  requirement_revision: number
  evaluation_status: string
  stage: string
  run_status: string | null
  evidence_references: string[]
  evaluation_window: Record<string, unknown>
  created_at: string
}

export const ACCEPTED_DOCUMENT_EXTENSIONS = ['.txt', '.md', '.markdown', '.pdf', '.docx'] as const
export const MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
