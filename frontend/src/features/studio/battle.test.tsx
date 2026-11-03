import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { combineState, combineStatus, comparisonRows, leaderOf, mergeLogs } from './battle'
import { CompareMetrics } from './CompareMetrics'
import { emptyState, MAX_LOGS, type StudioState } from './studioStore'
import type { LogEntry, Progress } from './studioTypes'

const progress = (overrides: Partial<Progress> = {}): Progress => ({
  run_id: 'r',
  timestep: 1000,
  total_timesteps: 20000,
  fraction: 0.05,
  episodes: 10,
  elapsed_seconds: 5,
  steps_per_second: 200,
  current_reward_avg: 50,
  mean_reward: 40,
  best_reward: 120,
  success_rate: 0.5,
  collisions: 0,
  disturbances: 0,
  last_termination: null,
  env_state: {},
  speed: 1,
  reward_per_step: 0.25,
  ...overrides,
})

const log = (seq: number, timestamp: string, message: string): LogEntry => ({
  seq,
  timestamp,
  session_id: 's',
  level: 'INFO',
  category: 'TRAINING',
  message,
  run_id: 'r',
  episode_id: null,
  meta: {},
})

describe('combineStatus', () => {
  it('prefers the state that can still be controlled', () => {
    expect(combineStatus('running', 'completed')).toBe('running')
    expect(combineStatus('paused', 'running')).toBe('running')
    expect(combineStatus('initialized', 'initialized')).toBe('initialized')
    expect(combineStatus('stopped', 'completed')).toBe('stopped')
    expect(combineStatus('completed', 'failed')).toBe('failed')
  })

  it('falls back to the side that exists', () => {
    expect(combineStatus(null, 'paused')).toBe('paused')
    expect(combineStatus('paused', null)).toBe('paused')
    expect(combineStatus(null, null)).toBeNull()
  })
})

describe('leaderOf', () => {
  it('names the higher moving average, and nobody on a tie or missing data', () => {
    expect(
      leaderOf(progress({ current_reward_avg: 80 }), progress({ current_reward_avg: 50 })),
    ).toBe('a')
    expect(
      leaderOf(progress({ current_reward_avg: 10 }), progress({ current_reward_avg: 50 })),
    ).toBe('b')
    expect(
      leaderOf(progress({ current_reward_avg: 50 }), progress({ current_reward_avg: 50 })),
    ).toBeNull()
    expect(leaderOf(progress({ current_reward_avg: null }), progress())).toBeNull()
    expect(leaderOf(null, progress())).toBeNull()
  })
})

describe('comparisonRows', () => {
  it('formats both sides from their own progress and shows dashes when a side has none', () => {
    const rows = comparisonRows(progress(), progress({ reward_per_step: null, episodes: 0 }))
    const perStep = rows.find((r) => r.label === 'Reward / step')
    expect(perStep).toEqual({ label: 'Reward / step', a: '0.250', b: '—' })
    expect(comparisonRows(null, null).every((r) => r.a === '—' && r.b === '—')).toBe(true)
  })
})

describe('mergeLogs', () => {
  it('interleaves both feeds by time and tags each line with its side', () => {
    const merged = mergeLogs(
      [log(1, '2026-01-01T00:00:01Z', 'a first'), log(2, '2026-01-01T00:00:03Z', 'a third')],
      [log(1, '2026-01-01T00:00:02Z', 'b second')],
    )
    expect(merged.map((l) => l.message)).toEqual(['[A] a first', '[B] b second', '[A] a third'])
  })

  it('stays bounded', () => {
    const many = Array.from({ length: MAX_LOGS + 50 }, (_, i) =>
      log(i, `2026-01-01T00:00:${String(i % 60).padStart(2, '0')}Z`, 'x'),
    )
    expect(mergeLogs(many, []).length).toBe(MAX_LOGS)
  })
})

describe('combineState', () => {
  it('keeps side A as the base and merges status, error and logs', () => {
    const a: StudioState = {
      ...emptyState,
      status: 'running',
      logs: [log(1, '2026-01-01T00:00:01Z', 'hi')],
      connection: 'live',
    }
    const b: StudioState = {
      ...emptyState,
      status: 'failed',
      error: 'B broke',
      connection: 'reconnecting',
    }
    const combined = combineState(a, b, 'Duel')
    expect(combined).toMatchObject({
      name: 'Duel',
      status: 'failed',
      error: 'B broke',
      connection: 'reconnecting',
    })
    expect(combined.logs[0].message).toBe('[A] hi')
  })
})

describe('CompareMetrics', () => {
  const state = (agent: string, avg: number): StudioState => ({
    ...emptyState,
    config: { agent, environment: 'cartpole', agent_params: {}, env_params: {}, training: {} },
    progress: progress({ current_reward_avg: avg }),
  })

  it('shows both sides and states who leads, with the caveat', () => {
    render(<CompareMetrics stateA={state('PPO', 90)} stateB={state('DQN', 30)} />)
    const table = screen.getByRole('table')
    expect(within(table).getByText('A · PPO')).toBeInTheDocument()
    expect(within(table).getByText('B · DQN')).toBeInTheDocument()
    expect(screen.getByText(/Side A has the higher moving-average reward/)).toBeInTheDocument()
    expect(screen.getByText(/not a significance test/)).toBeInTheDocument()
  })

  it('declines to name a leader before both sides have data', () => {
    const empty: StudioState = {
      ...state('DQN', 0),
      progress: progress({ current_reward_avg: null }),
    }
    render(<CompareMetrics stateA={state('PPO', 90)} stateB={empty} />)
    expect(screen.getByText(/No leader yet/)).toBeInTheDocument()
  })
})
