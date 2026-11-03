/**
 * Wire types for the studio API (`backend/api/routers/studio.py`).
 *
 * The backend owns every value here. The frontend only displays it.
 */

export type ParamKind = 'int' | 'float' | 'choice' | 'bool'
export type ParamValue = number | string | boolean

export interface ParamSpec {
  key: string
  label: string
  kind: ParamKind
  default: ParamValue
  help: string
  min: number | null
  max: number | null
  step: number | null
  options: string[]
}

export interface SpaceDescription {
  type: string
  n?: number
  shape?: number[]
  low?: Array<number | null>
  high?: Array<number | null>
}

export interface AgentTemplate {
  key: string
  name: string
  description: string
  family: string
  action_spaces: string[]
  params: ParamSpec[]
  reported_metrics: string[]
  compatible_environments: string[]
}

export interface EnvironmentTemplate {
  key: string
  name: string
  description: string
  dimension: '2D' | '3D'
  difficulty: string
  renderer: string
  observation_space: SpaceDescription
  action_space: SpaceDescription
  default_scene: Record<string, unknown>
  supports_disturbances: boolean
  params: ParamSpec[]
  compatible_agents: string[]
}

export interface Catalog {
  schema_version: string
  agents: AgentTemplate[]
  environments: EnvironmentTemplate[]
  training_params: ParamSpec[]
  net_arches: string[]
}

export type SessionStatus =
  | 'initialized'
  | 'running'
  | 'paused'
  | 'stopping'
  | 'stopped'
  | 'completed'
  | 'failed'

export const ACTIVE_STATUSES: readonly SessionStatus[] = ['running', 'paused', 'stopping']

export type ParamValues = Record<string, ParamValue>

export interface SessionConfig {
  agent: string
  environment: string
  agent_params: ParamValues
  env_params: ParamValues
  training: ParamValues
}

export interface Progress {
  run_id: string
  timestep: number
  total_timesteps: number
  fraction: number
  episodes: number
  elapsed_seconds: number
  steps_per_second: number
  current_reward_avg: number | null
  mean_reward: number | null
  best_reward: number | null
  success_rate: number | null
  collisions: number
  disturbances: number
  last_termination: string | null
  /** Latest environment state sampled by the backend (about 2 Hz). */
  env_state: Record<string, number>
  speed: number
}

export interface EpisodeRecord {
  episode: number
  timestep: number
  reward: number
  length: number
  success: boolean
  reason: string
  collisions: number
  disturbances: number
  moving_avg_reward: number
  success_rate: number
}

export interface UpdateRecord {
  timestep: number
  update: number
  policy_loss?: number
  value_loss?: number
  entropy?: number
  approx_kl?: number
  explained_variance?: number
  clip_fraction?: number
  loss?: number
  exploration_rate?: number
}

export interface EvaluationRecord {
  timestep: number
  episodes: number
  mean_reward: number
  std_reward: number
  mean_length: number
  success_rate: number
}

export interface CheckpointRecord {
  checkpoint_id: string
  session_id: string
  run_id: string
  timestep: number
  reason: string
  sha256: string
  size_bytes: number
  created_at: string
  algorithm: string
  environment: string
}

export interface FramePayload {
  timestep: number
  episode: number
  episode_step: number
  action: number | number[] | null
  reward: number
  episode_reward: number
  collision: boolean
  disturbance: boolean
  done: boolean
  initial?: boolean
  outcome?: { success: boolean; reason: string }
  state: Record<string, number>
}

export type LogLevel = 'INFO' | 'WARNING' | 'ERROR'
export type LogCategory =
  | 'TRAINING'
  | 'ENVIRONMENT'
  | 'AGENT'
  | 'FAULT'
  | 'RECOVERY'
  | 'CHECKPOINT'

export interface LogEntry {
  seq: number
  timestamp: string
  session_id: string
  level: LogLevel
  category: LogCategory
  message: string
  run_id: string
  episode_id: number | null
  meta: Record<string, unknown>
}

export interface SessionSummary {
  session_id: string
  run_id: string
  name: string
  status: SessionStatus
  pending_command: 'pause' | null
  agent: string
  environment: string
  config: SessionConfig
  created_at: string
  started_at: string | null
  finished_at: string | null
  error: string | null
  progress: Progress
  checkpoints: CheckpointRecord[]
}

export interface SessionSnapshot extends SessionSummary {
  scene: Record<string, unknown>
  episodes: EpisodeRecord[]
  updates: UpdateRecord[]
  evaluations: EvaluationRecord[]
  seq: number
  frame: FramePayload | null
  /** Recent `log` events (full envelopes) so a late or reconnecting client sees history. */
  logs?: StudioEvent[]
}

export interface CommandResult {
  session_id: string
  status: SessionStatus
  pending_command: 'pause' | null
  idempotent: boolean
}

export interface ExperimentSummary {
  session_id: string
  run_id: string
  name: string
  status: SessionStatus
  agent: string
  environment: string
  created_at: string
  finished_at: string | null
  progress: Progress
  checkpoints: CheckpointRecord[]
  error: string | null
}

/** Ordered event envelope published by `SessionHub.publish`. */
export interface StudioEvent {
  schema_version: string
  seq: number
  type: string
  session_id: string
  timestamp: string
  payload: Record<string, unknown>
}

export interface FrameMessage {
  type: 'frame'
  frame_seq: number
  session_id: string
  payload: FramePayload
}
