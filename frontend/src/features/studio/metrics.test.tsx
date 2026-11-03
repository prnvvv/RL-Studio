import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { findBestEpisode } from './bestEpisode'
import { MetricsPanel } from './MetricsPanel'
import { PPO } from './studioFixtures'
import { emptyState, type StudioState } from './studioStore'
import type { EpisodeRecord, Progress } from './studioTypes'

const episode = (n: number, reward: number): EpisodeRecord => ({
  episode: n,
  timestep: n * 100,
  reward,
  length: 50 + n,
  success: false,
  reason: 'pole_fell',
  collisions: 0,
  disturbances: 0,
  moving_avg_reward: reward,
  success_rate: 0,
})

const progress = (overrides: Partial<Progress> = {}): Progress => ({
  run_id: 'ses_aaaaaaaa_r1',
  timestep: 0,
  total_timesteps: 20000,
  fraction: 0,
  episodes: 0,
  elapsed_seconds: 0,
  steps_per_second: 0,
  current_reward_avg: null,
  mean_reward: null,
  best_reward: null,
  success_rate: null,
  collisions: 0,
  disturbances: 0,
  last_termination: null,
  env_state: {},
  speed: 1,
  ...overrides,
})

const stateWith = (overrides: Partial<StudioState>): StudioState => ({
  ...emptyState,
  sessionId: 'ses_aaaaaaaa',
  ...overrides,
})

describe('findBestEpisode', () => {
  it('returns the highest-reward episode, the earliest on a tie, and null when empty', () => {
    expect(findBestEpisode([])).toBeNull()
    expect(findBestEpisode([episode(1, 5), episode(2, 9), episode(3, 9)])?.episode).toBe(2)
  })
})

describe('MetricsPanel before and during training', () => {
  it('draws empty charts with the full timestep range and no best-episode banner before any episode', () => {
    render(<MetricsPanel state={stateWith({ progress: progress() })} agent={PPO} />)
    expect(screen.queryByTestId('best-episode')).toBeNull()
    expect(screen.queryByRole('img', { name: /no data recorded/i })).toBeNull()
    expect(screen.getAllByText('20k').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('Waiting for the first episode')).toHaveLength(2)
  })

  it('highlights the best episode so far', () => {
    const episodes = [episode(1, 12), episode(2, 187), episode(3, 40)]
    render(
      <MetricsPanel
        state={stateWith({ episodes, progress: progress({ best_reward: 187, episodes: 3 }) })}
        agent={PPO}
      />,
    )
    expect(screen.getByTestId('best-episode')).toHaveTextContent(
      'Best episode #2 — reward 187.00 over 52 steps',
    )
  })

  it('still reports the best reward when that episode is no longer in the kept window', () => {
    render(
      <MetricsPanel
        state={stateWith({ episodes: [episode(9, 3)], progress: progress({ best_reward: 500 }) })}
        agent={PPO}
      />,
    )
    expect(screen.getByTestId('best-episode')).toHaveTextContent('reward 500.00')
    expect(screen.getByTestId('best-episode')).toHaveTextContent('no longer kept')
  })
})
