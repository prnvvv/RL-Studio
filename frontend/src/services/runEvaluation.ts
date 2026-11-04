/**
 * Run-level policy evaluation service. Binds the evaluation routes in `backend/api/routers/evaluation.py`:
 *
 * - `POST /api/v1/runs/{run_id}/evaluations`                              roll the saved policy out and persist it
 * - `GET  /api/v1/runs/{run_id}/evaluations[/{id}]`                       history (append-only) / one record
 * - `POST /api/v1/incidents/{id}/recoveries/{recovery_id}/evaluate`       validate the policy a recovery produced
 *
 * Every number shown comes from episodes the backend actually played; this module never computes a metric.
 */
import type { ServiceResult } from './types'
import { api } from './client'

export interface EpisodeResult {
  seed: number
  reward: number
  episode_length: number
  success: boolean
  collision: boolean
  timed_out: boolean
  error: string | null
}

export interface EvaluationSummary {
  total_episode_count: number
  valid_episode_count: number
  failed_episode_count: number
  success_rate: number | null
  mean_reward: number | null
  median_reward: number | null
  mean_episode_length: number | null
  timeout_rate: number | null
  confidence_intervals?: {
    mean_reward?: { lower: number | null; upper: number | null } | null
    success_rate?: { lower: number | null; upper: number | null } | null
  }
}

export interface BaselineComparison {
  identity: {
    run_evaluation_id: string
    run_id: string
    artifact_id: string
    policy_fingerprint: string | null
    environment_version: string | null
    created_at: string
  }
  comparable: boolean
  paired?: boolean
  reason?: string
  deltas: Record<string, number | null> | null
}

export interface AcceptanceResult {
  status: 'passed' | 'failed' | 'inconclusive'
  checks: Array<{ criterion: string; threshold: number; measured: number | null; outcome: string }>
}

export interface RunEvaluation {
  run_evaluation_id: string
  project_id: string | null
  run_id: string
  artifact_id: string
  checkpoint_id: string | null
  policy_fingerprint: string | null
  agent_config_fingerprint: string | null
  algorithm: string | null
  environment_id: string | null
  environment_version: string | null
  environment_config: Record<string, unknown>
  status: 'completed' | 'passed' | 'failed' | 'inconclusive' | 'blocked'
  episode_count: number
  seeds: number[]
  metrics: {
    summary: EvaluationSummary | null
    variability: {
      reward_std: number | null
      reward_min: number | null
      reward_max: number | null
      length_std: number | null
    } | null
  }
  /** Present on a single-record read; `null` in lists. */
  episodes: EpisodeResult[] | null
  baseline: BaselineComparison | null
  acceptance: AcceptanceResult | null
  incident_id: string | null
  recovery_id: string | null
  purpose: string
  warnings: string[]
  errors: string[]
  details: Record<string, unknown>
  created_at: string
  completed_at: string | null
}

export interface RunEvaluationRequest {
  episodes?: number
  checkpoint_id?: string
  baseline_evaluation_id?: string
  minimum_mean_reward?: number
  minimum_success_rate?: number
}

export interface RecoveryEvaluationRequest {
  episodes?: number
  acceptance_criteria?: { minimum_recovered_success_rate?: number }
}

export interface RecoveryEvaluationResult {
  evaluation: {
    evaluation_id: string
    evaluation_status: string
    recovery_verification_status: string
    recovery_verified: boolean
    episode_count: number | null
    seeds: number[]
    baseline_mean_reward: number | null
    recovered_mean_reward: number | null
    baseline_success_rate: number | null
    recovered_success_rate: number | null
    reward_improvement: number | null
    warnings: string[]
    errors: string[]
  }
  rollouts: Record<string, string>
  recovered_policy: { artifact_id: string; policy_fingerprint: string | null }
  faulty_reference: string | null
  note: string | null
}

export interface RunEvaluationService {
  evaluateRun(runId: string, request: RunEvaluationRequest): Promise<ServiceResult<RunEvaluation>>
  listRunEvaluations(runId: string, signal?: AbortSignal): Promise<ServiceResult<RunEvaluation[]>>
  getRunEvaluation(runId: string, evaluationId: string): Promise<ServiceResult<RunEvaluation>>
  evaluateRecovery(
    incidentId: string,
    recoveryId: string,
    request: RecoveryEvaluationRequest,
  ): Promise<ServiceResult<RecoveryEvaluationResult>>
}

const seg = encodeURIComponent
const SLOW_MS = 180_000

export function createRunEvaluationService(): RunEvaluationService {
  return {
    evaluateRun: (runId, request) =>
      api.post<RunEvaluation>(`/api/v1/runs/${seg(runId)}/evaluations`, {
        jsonBody: request,
        timeoutMs: SLOW_MS,
      }),
    async listRunEvaluations(runId, signal) {
      const result = await api.get<{ evaluations: RunEvaluation[] }>(
        `/api/v1/runs/${seg(runId)}/evaluations`,
        { signal },
      )
      return result.state === 'ok' ? { state: 'ok', data: result.data.evaluations } : result
    },
    getRunEvaluation: (runId, evaluationId) =>
      api.get<RunEvaluation>(`/api/v1/runs/${seg(runId)}/evaluations/${seg(evaluationId)}`),
    evaluateRecovery: (incidentId, recoveryId, request) =>
      api.post<RecoveryEvaluationResult>(
        `/api/v1/incidents/${seg(incidentId)}/recoveries/${seg(recoveryId)}/evaluate`,
        { jsonBody: request, timeoutMs: SLOW_MS },
      ),
  }
}
