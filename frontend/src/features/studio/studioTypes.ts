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

/** Where a catalog entry comes from: shipped with the backend, or uploaded by the user. */
export type CatalogKind = 'builtin' | 'custom'

/** Architecture and provenance of an uploaded model, as inferred by the backend. */
export interface CustomModelInfo {
  model_id: string
  name: string
  original_filename: string
  format: 'zip' | 'pt'
  sha256: string
  size_bytes: number
  uploaded_at: string
  algorithm: string
  /** True when the algorithm label is inferred from the archive rather than stored in the weights. */
  algorithm_inferred: boolean
  obs_dim: number
  action_type: 'discrete' | 'box'
  action_dim: number
  net_arch: number[] | { pi: number[]; vf: number[] }
  activation: string
  /** True when the activation function could not be read and the SB3 default is assumed. */
  activation_assumed: boolean
}

export interface UploadedModel extends CustomModelInfo {
  key: string
}

/** Declarative warehouse-grid layout accepted as a custom environment. */
export interface GridLayout {
  name?: string
  rows: number
  cols: number
  start: number[]
  goal: number[]
  obstacles: number[][]
}

export interface CustomEnvironmentInfo {
  env_id: string
  uploaded_at: string
  layout: GridLayout
}

export interface UploadedEnvironment {
  env_id: string
  key: string
  name: string
  uploaded_at: string
  layout: GridLayout
}

export interface CatalogLimits {
  model_extensions: string[]
  max_model_bytes: number
  max_grid: number
}

export interface AgentTemplate {
  key: string
  /** Absent on older backends; treated as built-in. */
  kind?: CatalogKind
  custom?: CustomModelInfo
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
  kind?: CatalogKind
  custom?: CustomEnvironmentInfo
  name: string
  description: string
  dimension: '2D' | '3D'
  difficulty: string
  renderer: string
  observation_space: SpaceDescription
  action_space: SpaceDescription
  default_scene: Record<string, unknown>
  supports_disturbances: boolean
  /** Disturbances chaos mode can inject here. */
  chaos_kinds?: string[]
  params: ParamSpec[]
  compatible_agents: string[]
}

export interface Catalog {
  schema_version: string
  limits?: CatalogLimits
  agents: AgentTemplate[]
  environments: EnvironmentTemplate[]
  training_params: ParamSpec[]
  net_arches: string[]
}

export type SessionStatus =
  'initialized' | 'running' | 'paused' | 'stopping' | 'stopped' | 'completed' | 'failed'

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
  /** Reward of finished episodes per environment step. */
  reward_per_step?: number | null
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

/** Chaos-mode state (disturbances injected into the running environment). */
export interface ChaosState {
  enabled: boolean
  /** 0 (none) to 1 (maximum). */
  intensity: number
  kinds: string[]
  /** Disturbances injected so far (sensor noise is counted separately). */
  events: number
  noise_steps: number
}

export const DEFAULT_CHAOS: ChaosState = {
  enabled: false,
  intensity: 0.3,
  kinds: [],
  events: 0,
  noise_steps: 0,
}

/** Manual-control state published by the backend (`controls` in snapshots, `control` events). */
export interface ControlState {
  human: boolean
  human_steps: number
  /** True while the backend streams the policy's action preferences with each frame. */
  brain: boolean
  chaos: ChaosState
}

/** The policy's preference at one grid cell. */
export interface BrainCell {
  row: number
  col: number
  probs: number[]
  greedy: number
}

/**
 * What the agent "thinks" at the current observation, computed by the backend from
 * the live policy. `probs` are action probabilities (for DQN a softmax of `q`).
 */
export interface BrainPayload {
  kind: 'probs' | 'q' | 'gaussian'
  probs?: number[]
  q?: number[]
  probs_from?: string
  mean?: number[]
  std?: number[]
  greedy?: number
  executed: number | number[] | null
  grid?: BrainCell[]
}

export interface FramePayload {
  timestep: number
  episode: number
  episode_step: number
  action: number | number[] | null
  /** Who chose `action`: the agent, or a human who took manual control. */
  source?: 'agent' | 'human'
  /** Present only while the brain view is enabled. */
  brain?: BrainPayload
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
export type LogCategory = 'TRAINING' | 'ENVIRONMENT' | 'AGENT' | 'FAULT' | 'RECOVERY' | 'CHECKPOINT'

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
  /** `inference` when an uploaded model is run without learning. */
  mode?: 'training' | 'inference'
  controls?: ControlState
  /** Present when this session is one side of a battle. */
  battle?: { battle_id: string; side: 'a' | 'b' } | null
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

export type BattleSide = 'a' | 'b'

export interface BattleSideRequest {
  agent: string
  agent_params: ParamValues
}

export interface BattleRequest {
  environment: string
  name?: string
  env_params: ParamValues
  training: ParamValues
  a: BattleSideRequest
  b: BattleSideRequest
}

export interface BattleSideMetrics {
  timestep: number | null
  episodes: number | null
  current_reward_avg: number | null
  best_reward: number | null
  success_rate: number | null
  reward_per_step: number | null
  steps_per_second: number | null
}

export interface BattleComparison {
  metrics: Record<BattleSide, BattleSideMetrics>
  /** The side with the higher moving-average reward right now (not a significance test). */
  leader: BattleSide | null
  leader_basis: string
  same_environment: boolean
  same_seed: boolean
}

export interface BattleSnapshot {
  battle_id: string
  a: SessionSnapshot
  b: SessionSnapshot
  comparison: BattleComparison
}

/** Per-side outcome of a battle command; a side that could not comply reports why. */
export type BattleSideResult = CommandResult | { error: string; status: SessionStatus }

export interface BattleCommandResult {
  battle_id: string
  a: BattleSideResult
  b: BattleSideResult
}
