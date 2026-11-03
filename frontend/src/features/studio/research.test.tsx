import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { MetricsPanel } from './MetricsPanel'
import { countReasons, healthMetricsFor, histogram, lastN } from './metrics/metricData'
import { PPO } from './studioFixtures'
import { emptyState, StudioStore, type StudioState } from './studioStore'
import type {
  AgentTemplate,
  EpisodeRecord,
  EvaluationRecord,
  FramePayload,
  Progress,
  SessionConfig,
  UpdateRecord,
} from './studioTypes'
import {
  LAYOUT_KEY,
  MIN_CENTER,
  MIN_LEFT,
  MIN_METRICS,
  clampLayout,
  defaultLayout,
  loadLayout,
  saveLayout,
} from './workspaceLayout'

const episode = (n: number, over: Partial<EpisodeRecord> = {}): EpisodeRecord => ({
  episode: n,
  timestep: n * 100,
  reward: n,
  length: 50,
  success: false,
  reason: 'pole_fell',
  collisions: 0,
  disturbances: 0,
  moving_avg_reward: n,
  success_rate: 0,
  ...over,
})

const progress = (over: Partial<Progress> = {}): Progress => ({
  run_id: 'ses_aaaaaaaa_r1',
  timestep: 1000,
  total_timesteps: 20000,
  fraction: 0.05,
  episodes: 0,
  elapsed_seconds: 5,
  steps_per_second: 100,
  current_reward_avg: null,
  mean_reward: null,
  best_reward: null,
  success_rate: null,
  collisions: 3,
  disturbances: 0,
  last_termination: null,
  env_state: {},
  speed: 1,
  ...over,
})

const config: SessionConfig = {
  agent: 'PPO',
  environment: 'cartpole',
  agent_params: {},
  env_params: { max_episode_steps: 100 },
  training: {},
}

const stateWith = (over: Partial<StudioState>): StudioState => ({
  ...emptyState,
  sessionId: 'ses_aaaaaaaa',
  progress: progress(),
  config,
  ...over,
})

const sac: AgentTemplate = {
  ...PPO,
  key: 'SAC',
  name: 'SAC',
  reported_metrics: ['actor_loss', 'critic_loss', 'ent_coef'],
}

describe('metric helpers', () => {
  it('keeps the last N points or everything', () => {
    const items = Array.from({ length: 250 }, (_, i) => i)
    expect(lastN(items, '100')).toHaveLength(100)
    expect(lastN(items, '100')[0]).toBe(150)
    expect(lastN(items, '1000')).toHaveLength(250)
    expect(lastN(items, 'all')).toHaveLength(250)
  })

  it('bins values into equal-width buckets, and handles constant and empty input', () => {
    const bins = histogram([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 5)
    expect(bins).toHaveLength(5)
    expect(bins.reduce((sum, b) => sum + b.count, 0)).toBe(11)
    expect(bins[4].count).toBe(3) // the maximum lands in the last bin, not past it
    expect(histogram([7, 7, 7])).toEqual([{ from: 7, to: 7, count: 3 }])
    expect(histogram([])).toEqual([])
    expect(histogram([Number.NaN, 3])).toEqual([{ from: 3, to: 3, count: 1 }])
  })

  it('counts the environment-reported termination reasons, most common first', () => {
    const counts = countReasons([
      { reason: 'goal_reached' },
      { reason: 'collision' },
      { reason: 'collision' },
      { reason: '' },
    ])
    expect(counts.map((c) => [c.reason, c.count])).toEqual([
      ['collision', 2],
      ['goal_reached', 1],
      ['unknown', 1],
    ])
    expect(counts[0].share).toBe(0.5)
    expect(countReasons([])).toEqual([])
  })

  it('lists health metrics only for what the algorithm reports', () => {
    expect(healthMetricsFor(sac).map((m) => m.key)).toEqual([
      'actor_loss',
      'critic_loss',
      'ent_coef',
    ])
    expect(healthMetricsFor(undefined)).toEqual([])
    const a2c = { ...PPO, reported_metrics: ['policy_loss', 'value_loss', 'entropy'] }
    expect(healthMetricsFor(a2c).map((m) => m.key)).not.toContain('approx_kl')
  })
})

describe('workspace layout', () => {
  beforeEach(() => window.localStorage.clear())

  it('defaults to roughly 30% / 40% / 30%', () => {
    const layout = defaultLayout(1440)
    expect(layout.left).toBe(432)
    expect(layout.metrics).toBe(432)
    expect(1440 - layout.left - layout.metrics).toBe(576)
  })

  it('never lets a zone collapse or the simulation shrink below its minimum', () => {
    const tiny = clampLayout({ left: 10, metrics: 10, dock: 5 }, 1440)
    expect(tiny.left).toBe(MIN_LEFT)
    expect(tiny.metrics).toBe(MIN_METRICS)
    expect(tiny.dock).toBeGreaterThanOrEqual(120)
    const greedy = clampLayout({ left: 700, metrics: 700, dock: 300 }, 1440)
    expect(1440 - greedy.left - greedy.metrics).toBeGreaterThanOrEqual(MIN_CENTER)
    expect(greedy.left).toBeGreaterThanOrEqual(MIN_LEFT)
    expect(greedy.metrics).toBeGreaterThanOrEqual(MIN_METRICS)
  })

  it('gives room back to the metrics panel first when the window shrinks', () => {
    const shrunk = clampLayout({ left: 432, metrics: 432, dock: 260 }, 1100)
    expect(shrunk.left).toBe(432)
    expect(shrunk.metrics).toBeLessThan(432)
    expect(1100 - shrunk.left - shrunk.metrics).toBeGreaterThanOrEqual(MIN_CENTER)
  })

  it('persists sizes between sessions and ignores corrupt storage', () => {
    saveLayout({ left: 500, metrics: 350, dock: 200 })
    expect(JSON.parse(window.localStorage.getItem(LAYOUT_KEY) ?? '{}')).toMatchObject({
      left: 500,
      metrics: 350,
    })
    expect(loadLayout(1600)).toEqual({ left: 500, metrics: 350, dock: 200 })
    window.localStorage.setItem(LAYOUT_KEY, '{not json')
    expect(loadLayout(1440)).toEqual(defaultLayout(1440))
    window.localStorage.setItem(LAYOUT_KEY, JSON.stringify({ left: 1 }))
    expect(loadLayout(1440)).toEqual(defaultLayout(1440))
  })
})

describe('research metrics panel', () => {
  it('keeps the existing metrics and adds the four sections', () => {
    render(<MetricsPanel state={stateWith({})} agent={PPO} />)
    expect(screen.getByRole('progressbar', { name: 'Training progress' })).toBeInTheDocument()
    expect(screen.getByText('Success rate', { selector: 'h4' })).toBeInTheDocument()
    for (const title of [
      'Training progress',
      'Algorithm health',
      'Episode statistics',
      'Environment dynamics',
    ]) {
      expect(screen.getByText(title, { selector: 'summary' })).toBeInTheDocument()
    }
  })

  it('shows "Waiting for data" for every health chart before its first value', () => {
    const algo = { ...PPO, reported_metrics: ['policy_loss', 'value_loss', 'entropy', 'approx_kl'] }
    render(<MetricsPanel state={stateWith({})} agent={algo} />)
    for (const title of ['Policy loss', 'Value loss', 'Entropy', 'Approx. KL divergence']) {
      const card = screen.getByRole('region', { name: title })
      expect(within(card).getByText('Waiting for data')).toBeInTheDocument()
    }
  })

  it('draws real values per algorithm: PPO health stats, and SAC actor/critic losses instead', () => {
    const updates: UpdateRecord[] = [
      { timestep: 100, update: 1, actor_loss: -1.5, critic_loss: 80, ent_coef: 0.9 },
      { timestep: 200, update: 2, actor_loss: -2.5, critic_loss: 60, ent_coef: 0.8 },
    ]
    render(<MetricsPanel state={stateWith({ updates })} agent={sac} />)
    expect(
      within(screen.getByRole('region', { name: 'Actor loss' })).getByText('-2.500'),
    ).toBeInTheDocument()
    expect(
      within(screen.getByRole('region', { name: 'Critic loss' })).getByText('60.000'),
    ).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Approx. KL divergence' })).toBeNull() // SAC does not report it
    // The charts that now have values no longer wait.
    expect(
      within(screen.getByRole('region', { name: 'Actor loss' })).queryByText('Waiting for data'),
    ).toBeNull()
    expect(
      within(screen.getByRole('region', { name: 'Entropy coefficient' })).queryByText(
        'Waiting for data',
      ),
    ).toBeNull()
  })

  it('overlays the deterministic evaluation reward as a separate dashed series', () => {
    const evaluations: EvaluationRecord[] = [
      {
        timestep: 2000,
        episodes: 3,
        mean_reward: 120,
        std_reward: 5,
        mean_length: 120,
        success_rate: 1,
      },
    ]
    const { container, rerender } = render(
      <MetricsPanel state={stateWith({ episodes: [episode(1), episode(2)] })} agent={PPO} />,
    )
    expect(container.querySelector('path[stroke-dasharray="6 4"]')).toBeNull() // none before the first evaluation
    rerender(
      <MetricsPanel
        state={stateWith({ episodes: [episode(1), episode(2)], evaluations })}
        agent={PPO}
      />,
    )
    const reward = screen.getByRole('region', { name: 'Reward vs. timestep' })
    expect(reward.querySelector('path[stroke-dasharray="6 4"]')).not.toBeNull()
    expect(within(reward).getByText(/Evaluation reward \(deterministic\)/)).toBeInTheDocument()
  })

  it('breaks episodes down by the termination reasons the environment reported', () => {
    const episodes = [
      ...Array.from({ length: 6 }, (_, i) => episode(i + 1, { reason: 'crashed' })),
      ...Array.from({ length: 2 }, (_, i) => episode(i + 10, { reason: 'landed', success: true })),
    ]
    render(<MetricsPanel state={stateWith({ episodes })} agent={PPO} />)
    const card = screen.getByRole('region', { name: 'Termination reasons' })
    expect(within(card).getByText(/6 · 75%/)).toBeInTheDocument()
    expect(within(card).getByText(/2 · 25%/)).toBeInTheDocument()
    expect(within(card).getAllByTestId('reason-segment')).toHaveLength(2)
  })

  it('narrows the episode-length histogram with the time range selector', () => {
    const episodes = [
      ...Array.from({ length: 50 }, (_, i) => episode(i + 1, { length: 10 })),
      ...Array.from({ length: 100 }, (_, i) => episode(i + 51, { length: 20 })),
    ]
    render(<MetricsPanel state={stateWith({ episodes })} agent={PPO} />)
    const card = screen.getByRole('region', { name: 'Episode length' })
    expect(within(card).getByText('mean 16.7')).toBeInTheDocument() // all 150 episodes
    fireEvent.click(within(card).getByRole('button', { name: 'Last 100' }))
    expect(within(card).getByText('mean 20.0')).toBeInTheDocument() // only the recent ones
    expect(within(card).getByRole('button', { name: 'Last 100' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  it('shows the live episode step against its limit from the frame stream', () => {
    const store = new StudioStore()
    const frame: FramePayload = {
      timestep: 5,
      episode: 2,
      episode_step: 40,
      action: 1,
      reward: 1,
      episode_reward: 40,
      collision: false,
      disturbance: false,
      done: false,
      state: { distance_to_goal: 12 },
    }
    store.applyFrame(frame)
    render(<MetricsPanel state={stateWith({})} agent={PPO} store={store} />)
    expect(screen.getByText('40 / 100')).toBeInTheDocument()
    const bar = screen.getByRole('progressbar', { name: 'Episode step' })
    expect(bar).toHaveAttribute('aria-valuenow', '40')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
    expect(screen.getByText('Distance to goal')).toBeInTheDocument()
    const dynamics = screen
      .getByText('Environment dynamics', { selector: 'summary' })
      .closest('details')!
    expect(within(dynamics).getByText('Collisions').nextSibling).toHaveTextContent('3')
  })

  it('omits the distance readout for environments that have no goal', () => {
    const store = new StudioStore()
    render(<MetricsPanel state={stateWith({})} agent={PPO} store={store} />)
    expect(screen.queryByText('Distance to goal')).toBeNull()
  })
})
