import { describe, expect, it } from 'vitest'
import type { Evaluation } from '../../schemas/evaluation'
import {
  comparisonSeries,
  comparisonRows,
  criteriaRows,
  improvementRows,
  outcomeClaim,
} from './evaluationPresentation'

const CREATED = '2026-11-02T00:03:00Z'

export function evaluation(overrides: Partial<Evaluation> = {}): Evaluation {
  return {
    evaluation_id: 'eval_1',
    incident_id: 'inc_demo',
    recovery_id: 'rec_1',
    baseline_run_id: 'run_healthy',
    recovered_run_id: 'run_recovered',
    evaluation_status: 'passed',
    evaluation_environment_version: 'warehouse_v1',
    baseline_mean_reward: 95.5,
    recovered_mean_reward: 94.25,
    baseline_success_rate: 0.9,
    recovered_success_rate: 0.852,
    baseline_episode_length: 820.4,
    recovered_episode_length: 831.6,
    reward_improvement: null,
    success_rate_improvement: null,
    evaluation_metrics: {},
    comparison_results: {},
    acceptance_criteria: { minimum_recovered_success_rate: 0.8, require_no_episode_errors: true },
    recovery_verification_status: 'passed',
    recovery_verified: true,
    episode_count: 20,
    seeds: [0, 1, 2],
    evidence_ids: [],
    warnings: [],
    errors: [],
    details: {},
    created_at: CREATED,
    completed_at: CREATED,
    ...overrides,
  }
}

describe('comparisonSeries', () => {
  it('reports the faulty series as not supplied when the record omits it', () => {
    const info = comparisonSeries(evaluation())
    expect(info.hasBaseline).toBe(true)
    expect(info.hasRecovered).toBe(true)
    expect(info.hasFaulty).toBe(false)
  })

  it('reports the faulty series as supplied when the record carries it', () => {
    const info = comparisonSeries(evaluation({ evaluation_metrics: { faulty_mean_reward: 40 } }))
    expect(info.hasFaulty).toBe(true)
  })
})

describe('comparisonRows', () => {
  it('shows supplied aggregates only from the record fields', () => {
    const [recovered] = comparisonRows(evaluation())
    expect(recovered?.columns.reward).toBe('94.25')
    expect(recovered?.columns.success).toBe('85.2%')
    expect(recovered?.columns.length).toBe('832')
  })

  it('uses Not available for missing measurements, never a zero', () => {
    const record = evaluation({
      baseline_mean_reward: null,
      baseline_success_rate: null,
      baseline_episode_length: null,
    })
    const [, baseline] = comparisonRows(record)
    expect(baseline?.columns.reward).toBe('Not available')
    expect(baseline?.columns.success).toBe('Not available')
    expect(baseline?.columns.length).toBe('Not available')
  })

  it('reports the faulty row as not supplied rather than zero-filled', () => {
    const [, , faulty] = comparisonRows(evaluation())
    expect(faulty?.series).toBe('Faulty baseline')
    expect(faulty?.columns.reward).toBe('Not supplied')
  })

  it('renders supplied faulty aggregates verbatim from evaluation_metrics', () => {
    const record = evaluation({
      evaluation_metrics: {
        faulty_mean_reward: 40,
        faulty_success_rate: 0.2,
        faulty_episode_length: 210,
      },
    })
    const [, , faulty] = comparisonRows(record)
    expect(faulty?.columns.reward).toBe('40')
    expect(faulty?.columns.success).toBe('0.2')
  })
})

describe('improvementRows', () => {
  it('presents recorded deltas verbatim and missing deltas as Not computed', () => {
    const record = evaluation({ reward_improvement: -1.25, success_rate_improvement: null })
    const rows = improvementRows(record)
    expect(rows[0]?.columns.reward).toBe('-1.2500')
    expect(rows[1]?.columns.reward).toBe('Not computed')
  })
})

describe('criteriaRows', () => {
  it('renders only the criteria the record configured', () => {
    const rows = criteriaRows(evaluation())
    expect(rows).toHaveLength(2)
    expect(rows[0]).toEqual({
      key: 'minimum_recovered_success_rate',
      label: expect.any(String),
      value: '0.8',
    })
    expect(rows[1]).toEqual({
      key: 'require_no_episode_errors',
      label: expect.any(String),
      value: 'Required',
    })
  })

  it('hands an unconfigured-criteria record to the UI with zero rows', () => {
    const record = evaluation({ acceptance_criteria: {} })
    expect(criteriaRows(record)).toEqual([])
  })
})

describe('outcomeClaim', () => {
  it('carries the backend verdict verbatim, including inconclusive', () => {
    expect(outcomeClaim(evaluation())).toMatchObject({ outcome: 'passed', recovery_verified: true })
    const inconclusive = outcomeClaim(
      evaluation({ evaluation_status: 'inconclusive', recovery_verified: false }),
    )
    expect(inconclusive.outcome).toBe('inconclusive')
    expect(inconclusive.recovery_verified).toBe(false)
    expect(inconclusive.label).toMatch(/inconclusive/i)
  })

  it('never reports success for a not_run evaluation', () => {
    const claim = outcomeClaim(
      evaluation({ evaluation_status: 'not_run', recovery_verified: false }),
    )
    expect(claim.outcome).toBe('not_run')
    expect(claim.label).toMatch(/has not been run/i)
  })
})
