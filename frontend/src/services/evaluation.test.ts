import { afterEach, describe, expect, it, vi } from 'vitest'
import { createEvaluationService, evaluationItemPath, evaluationPath } from './evaluation'
import { buildRequestUrl } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const EVALUATION_BODY = {
  evaluation_id: 'eval_1',
  incident_id: 'inc_demo',
  recovery_id: 'rec_1',
  baseline_run_id: 'run_healthy',
  recovered_run_id: 'run_recovered',
  evaluation_status: 'passed',
  evaluation_environment_version: 'warehouse_v1',
  baseline_mean_reward: 95.5,
  recovered_mean_reward: 94.2,
  baseline_success_rate: 0.9,
  recovered_success_rate: 0.86,
  baseline_episode_length: 820,
  recovered_episode_length: 832,
  reward_improvement: null,
  success_rate_improvement: null,
  evaluation_metrics: {},
  comparison_results: {},
  acceptance_criteria: {},
  recovery_verification_status: 'passed',
  recovery_verified: true,
  episode_count: 20,
  seeds: [0, 1, 2],
  evidence_ids: [],
  warnings: [],
  errors: [],
  details: {},
  created_at: '2026-11-02T00:03:00Z',
  completed_at: '2026-11-02T00:05:00Z',
}

describe('planned request paths', () => {
  it('encodes ids into the evaluation paths', () => {
    expect(buildRequestUrl('http://localhost:8000', evaluationPath('inc/1'))).toBe(
      'http://localhost:8000/api/v1/incidents/inc%2F1/evaluations',
    )
    expect(buildRequestUrl('http://localhost:8000', evaluationItemPath('inc/1', 'e/2'))).toBe(
      'http://localhost:8000/api/v1/incidents/inc%2F1/evaluations/e%2F2',
    )
  })
})

describe('evaluation service', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const service = createEvaluationService()

  it('posts evaluation requests with episode records verbatim', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, EVALUATION_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const request = {
      recovery_id: 'rec_1',
      baseline_run_id: 'run_healthy',
      baseline_checkpoint_id: 'ckpt_healthy',
      recovered_run_id: 'run_recovered',
      recovered_checkpoint_id: 'ckpt_recovered',
      evaluation_environment_version: 'warehouse_v1',
      environment_healthy: true,
      baseline_episodes: [
        {
          episode_id: 'e1',
          seed: 0,
          reward: 96,
          episode_length: 815,
          success: true,
          collision: false,
          timed_out: false,
          error: null,
          metadata: {},
        },
      ],
      recovered_episodes: [
        {
          episode_id: 'e2',
          seed: 0,
          reward: 94,
          episode_length: 830,
          success: true,
          collision: false,
          timed_out: false,
          error: null,
          metadata: {},
        },
      ],
      // No faulty baseline supplied: omitted entirely, never zero-filled.
      acceptance_criteria: { minimum_recovered_success_rate: 0.8 },
      idempotency_key: 'eval-key-1',
    }

    const result = await service.createEvaluation('inc_demo', request)

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/incidents/inc_demo/evaluations')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual(request)
    expect(result.state).toBe('ok')
    if (result.state === 'ok') {
      // Backend-computed acceptance is passed through untouched.
      expect(result.data.recovery_verified).toBe(true)
      expect(result.data.evaluation_status).toBe('passed')
    }
  })

  it('preserves an inconclusive outcome instead of softening it', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(201, {
        ...EVALUATION_BODY,
        evaluation_status: 'inconclusive',
        recovery_verification_status: 'inconclusive',
        recovery_verified: false,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await service.createEvaluation('inc_demo', {
      baseline_run_id: 'run_healthy',
      baseline_checkpoint_id: 'ckpt_healthy',
      recovered_run_id: 'run_recovered',
      recovered_checkpoint_id: 'ckpt_recovered',
      evaluation_environment_version: 'warehouse_v1',
      environment_healthy: true,
      baseline_episodes: [],
      recovered_episodes: [],
    })

    expect(result.state).toBe('ok')
    if (result.state === 'ok') {
      expect(result.data.evaluation_status).toBe('inconclusive')
      expect(result.data.recovery_verified).toBe(false)
    }
  })

  it('fetches a recorded evaluation by id from the live endpoint', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, EVALUATION_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const result = await service.getEvaluation('inc_demo', 'eval_1')

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/incidents/inc_demo/evaluations/eval_1')
    expect(init.method).toBe('GET')
    expect(result.state).toBe('ok')
  })
})
