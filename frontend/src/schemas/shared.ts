/**
 * Frontend types mirroring shared/schemas (keep in sync with backend).
 * Root AGENTS.md §7: use canonical types; do not duplicate arbitrarily.
 */

export type UUID = string
export type ISODateTime = string

export const SCHEMA_VERSION = '1.0' as const

export type SourceComponent =
  | 'environment'
  | 'training'
  | 'monitoring'
  | 'fault_injection'
  | 'verification'
  | 'diagnosis'
  | 'provenance'
  | 'recovery'
  | 'evaluation'

export interface ExecutionEventEnvelope {
  schema_version: string
  event_id: UUID
  event_type: string
  run_id: UUID
  project_id?: UUID | null
  experiment_id?: UUID | null
  environment_id?: string | null
  environment_version?: string | null
  episode_id?: UUID | null
  rollout_id?: UUID | null
  training_update_id?: UUID | null
  timestep: number
  sequence: number
  timestamp: ISODateTime
  source_component: SourceComponent
  source_version?: string | null
  correlation_id?: string | null
  cause_id?: string | null
  extensions?: Record<string, unknown>
}

export interface EpisodeStartedPayload {
  seed?: number | null
}

export interface EpisodeStartedEvent extends ExecutionEventEnvelope {
  event_type: 'episode_started'
  payload: EpisodeStartedPayload
}

export interface EpisodeEndedPayload {
  total_reward: number
  steps: number
  terminated: boolean
  truncated: boolean
  success: boolean
}

export interface EpisodeEndedEvent extends ExecutionEventEnvelope {
  event_type: 'episode_ended'
  payload: EpisodeEndedPayload
}

export interface RewardObservedPayload {
  actual_reward: number
  expected_reward?: number | null
  reward_kind: string
  requirement_id?: string | null
}

export interface RewardObservedEvent extends ExecutionEventEnvelope {
  event_type: 'reward_observed'
  payload: RewardObservedPayload
}

export type ExecutionEvent = EpisodeStartedEvent | EpisodeEndedEvent | RewardObservedEvent

export interface Requirement {
  id: string
  version: string
  schema_version: string
  title: string
  description: string
  requirement_type: string
  source: string
  status: string
  operator?: string | null
  expected_value?: unknown
  tolerance?: number | null
  environment_version?: string | null
  agent_config_fingerprint?: string | null
  created_at?: ISODateTime | null
  confirmed_by?: string | null
  created_by?: string | null
  change_history?: Array<Record<string, unknown>>
  extensions?: Record<string, unknown>
}

export type IncidentStatus = 'open' | 'investigating' | 'resolved' | 'wont_fix' | 'false_positive'
export type ViolationSeverity = 'low' | 'medium' | 'high' | 'critical'
export type RootCauseStatus = 'confirmed' | 'probable' | 'unresolved'

export interface Incident {
  incident_id: UUID
  schema_version: string
  run_id: UUID
  requirement_id?: string | null
  environment_version?: string | null
  environment_id?: string | null
  violation_type: string
  severity: ViolationSeverity
  status: IncidentStatus
  detection_status: string
  diagnosis_status: RootCauseStatus
  evidence_event_ids: string[]
  evidence_refs: string[]
  detector_id?: string | null
  detector_version?: string | null
  created_at?: string | null
  resolved_at?: string | null
  extensions?: Record<string, unknown>
}

export type RecoveryStatus =
  'planned' | 'validating' | 'approved' | 'executing' | 'succeeded' | 'failed' | 'blocked'

export type RecoveryAction = 'restore_checkpoint' | 'collect_fresh_experience' | 'resume_training'

export interface CompatibilityCheck {
  name: string
  passed: boolean
  detail?: string | null
}

export interface Recovery {
  recovery_id: UUID
  schema_version: string
  incident_id: UUID
  proposed_actions: RecoveryAction[]
  executed_actions: RecoveryAction[]
  source_checkpoint_id?: string | null
  target_checkpoint_id?: string | null
  environment_fingerprint?: string | null
  agent_config_fingerprint?: string | null
  compatibility_checks: CompatibilityCheck[]
  approval_state: string
  status: RecoveryStatus
  failure_reason?: string | null
  evaluation_id?: string | null
  created_at?: string | null
  updated_at?: string | null
  extensions?: Record<string, unknown>
}

export type EvaluationStatus = 'pending' | 'running' | 'completed' | 'failed' | 'inconclusive'

export interface MetricResult {
  name: string
  value: number
  unit?: string | null
  baseline_value?: number | null
  delta?: number | null
}

export interface Evaluation {
  evaluation_id: UUID
  schema_version: string
  recovery_id?: string | null
  run_id?: string | null
  evaluation_environment_version?: string | null
  evaluation_policy_fingerprint?: string | null
  episode_count: number
  seeds: number[]
  metrics: MetricResult[]
  baseline_ids: string[]
  confidence_intervals?: Record<string, [number, number]> | null
  status: EvaluationStatus
  created_at?: string | null
  completed_at?: string | null
  extensions?: Record<string, unknown>
}
