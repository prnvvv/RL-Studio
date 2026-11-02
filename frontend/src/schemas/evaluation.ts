/**
 * Evaluation contracts — LIVE Person 4 endpoints.
 *
 * Mirrors `backend/evaluation/models.py` exactly as served by the mounted
 * `evaluation.p4_router` (`backend/api/routers/evaluation.py`):
 * - `POST /api/v1/incidents/{incident_id}/evaluations`             -> 201 Evaluation
 * - `GET  /api/v1/incidents/{incident_id}/evaluations/{eval_id}`   -> Evaluation
 *
 * Semantic guards mirrored from the backend (`frontend/AGENTS.md` §14.4):
 * - `inconclusive` is a first-class outcome; mixed or weak results are
 *   reported inconclusive, never rounded into success.
 * - `recovery_verified` / `recovery_verification_status` come only from the
 *   backend's acceptance checks — the frontend never computes acceptance.
 * - `faulty_episodes` may legitimately be empty (no faulty baseline was
 *   supplied); comparisons involving them are then unavailable, not zero.
 */
import type { ISODateTime } from './shared'

/** Evaluation outcome (`EvaluationStatus`). */
export type EvaluationStatus = 'passed' | 'failed' | 'inconclusive' | 'not_run' | 'blocked'

/** One recorded evaluation episode (`EpisodeEvaluation`). */
export interface EvaluationEpisode {
  episode_id: string | null
  /** Non-negative seed, as validated by the backend. */
  seed: number
  reward: number
  /** Non-negative step count, as validated by the backend. */
  episode_length: number
  success: boolean
  collision: boolean
  timed_out: boolean
  error: string | null
  metadata: Record<string, unknown>
}

/** Configured acceptance criteria recorded with the request (`AcceptanceCriteria`).
 * Every field is optional: only the criteria the caller configured are set. */
export interface AcceptanceCriteria {
  minimum_recovered_success_rate?: number | null
  minimum_success_rate_improvement_vs_faulty?: number | null
  maximum_success_rate_regression_vs_healthy?: number | null
  minimum_mean_reward_improvement_vs_faulty?: number | null
  maximum_mean_reward_regression_vs_healthy?: number | null
  maximum_collision_rate?: number | null
  maximum_timeout_rate?: number | null
  minimum_valid_episodes_per_group?: number | null
  require_no_episode_errors?: boolean
}

/** Create-evaluation request body (`EvaluationCreateRequest`). */
export interface EvaluationCreateRequest {
  recovery_id?: string | null
  baseline_run_id: string
  baseline_checkpoint_id: string
  recovered_run_id: string
  recovered_checkpoint_id: string
  /** Optional faulty-baseline identity; required when faulty episodes exist. */
  faulty_run_id?: string | null
  faulty_checkpoint_id?: string | null
  evaluation_environment_version: string
  environment_healthy: boolean
  baseline_episodes: EvaluationEpisode[]
  recovered_episodes: EvaluationEpisode[]
  faulty_episodes?: EvaluationEpisode[]
  acceptance_criteria?: AcceptanceCriteria
  evidence_ids?: string[]
  details?: Record<string, unknown>
  /** Idempotency protection for retried evaluation submissions. */
  idempotency_key?: string | null
}

/** Evaluation result with backend-computed acceptance (`Evaluation`). */
export interface Evaluation {
  evaluation_id: string
  incident_id: string
  recovery_id: string | null
  baseline_run_id: string | null
  recovered_run_id: string | null
  evaluation_status: EvaluationStatus
  evaluation_environment_version: string | null
  baseline_mean_reward: number | null
  recovered_mean_reward: number | null
  baseline_success_rate: number | null
  recovered_success_rate: number | null
  baseline_episode_length: number | null
  recovered_episode_length: number | null
  reward_improvement: number | null
  success_rate_improvement: number | null
  evaluation_metrics: Record<string, unknown>
  comparison_results: Record<string, unknown>
  acceptance_criteria: Record<string, unknown>
  /** The backend's own verdict on the recovery, from its acceptance policy. */
  recovery_verification_status: EvaluationStatus
  recovery_verified: boolean
  episode_count: number | null
  seeds: number[]
  evidence_ids: string[]
  warnings: string[]
  errors: string[]
  details: Record<string, unknown>
  created_at: ISODateTime
  completed_at: ISODateTime | null
}
