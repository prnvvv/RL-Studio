import type { AgentTemplate, EpisodeRecord } from '../studioTypes'

/** How much history a chart shows: the last N data points, or everything kept in the browser. */
export type RangeKey = '100' | '1000' | 'all'

export const RANGES: ReadonlyArray<{ key: RangeKey; label: string }> = [
  { key: '100', label: 'Last 100' },
  { key: '1000', label: 'Last 1000' },
  { key: 'all', label: 'All' },
]

export function lastN<T>(items: readonly T[], range: RangeKey): T[] {
  if (range === 'all') return [...items]
  const count = Number(range)
  return items.length <= count ? [...items] : items.slice(items.length - count)
}

export interface HistogramBin {
  from: number
  to: number
  count: number
}

/** Equal-width bins between the smallest and largest value. One bin when every value is equal. */
export function histogram(values: readonly number[], bins = 10): HistogramBin[] {
  const finite = values.filter((v) => Number.isFinite(v))
  if (finite.length === 0) return []
  const min = Math.min(...finite)
  const max = Math.max(...finite)
  if (min === max) return [{ from: min, to: max, count: finite.length }]
  const width = (max - min) / bins
  const out: HistogramBin[] = Array.from({ length: bins }, (_, i) => ({
    from: min + i * width,
    to: min + (i + 1) * width,
    count: 0,
  }))
  for (const value of finite) {
    const index = Math.min(bins - 1, Math.floor((value - min) / width))
    out[index].count += 1
  }
  return out
}

export interface ReasonCount {
  reason: string
  count: number
  share: number
}

/** How many episodes ended for each reason the environment reported, most common first. */
export function countReasons(episodes: readonly Pick<EpisodeRecord, 'reason'>[]): ReasonCount[] {
  const counts = new Map<string, number>()
  for (const episode of episodes) {
    const reason = episode.reason || 'unknown'
    counts.set(reason, (counts.get(reason) ?? 0) + 1)
  }
  const total = episodes.length
  return [...counts.entries()]
    .map(([reason, count]) => ({ reason, count, share: total === 0 ? 0 : count / total }))
    .sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason))
}

/** The training statistics SB3 logs, with what each one tells a researcher. */
export interface HealthMetric {
  key: string
  label: string
  hint: string
}

const HEALTH: Record<string, HealthMetric> = {
  policy_loss: {
    key: 'policy_loss',
    label: 'Policy loss',
    hint: 'The actor objective. It should settle rather than keep swinging.',
  },
  value_loss: {
    key: 'value_loss',
    label: 'Value loss',
    hint: 'Error of the value function. Spikes mean unstable value estimates.',
  },
  entropy: {
    key: 'entropy',
    label: 'Entropy',
    hint: 'Low entropy: premature convergence. High entropy: the policy is still close to random.',
  },
  approx_kl: {
    key: 'approx_kl',
    label: 'Approx. KL divergence',
    hint: 'How far each update moves the policy. If it explodes, training is unstable (PPO).',
  },
  explained_variance: {
    key: 'explained_variance',
    label: 'Explained variance',
    hint: 'Value-function quality. Close to 1.0 is good; at or below 0 it is no better than a constant.',
  },
  clip_fraction: {
    key: 'clip_fraction',
    label: 'Clip fraction',
    hint: 'Share of samples PPO clipped. Persistently high means the policy is being held back hard.',
  },
  loss: { key: 'loss', label: 'Loss', hint: 'Temporal-difference loss of the Q-network.' },
  exploration_rate: {
    key: 'exploration_rate',
    label: 'Exploration rate',
    hint: 'Epsilon: the chance of a random action. It anneals over the exploration fraction.',
  },
  actor_loss: { key: 'actor_loss', label: 'Actor loss', hint: 'Objective of the policy network.' },
  critic_loss: {
    key: 'critic_loss',
    label: 'Critic loss',
    hint: 'Error of the Q-value critics. Rising values mean the targets are drifting.',
  },
  ent_coef: {
    key: 'ent_coef',
    label: 'Entropy coefficient',
    hint: 'The auto-tuned temperature that trades reward for exploration (SAC).',
  },
  ent_coef_loss: {
    key: 'ent_coef_loss',
    label: 'Entropy coefficient loss',
    hint: 'Loss of the temperature tuner (SAC).',
  },
}

/** Charts for exactly the statistics this algorithm reports. Metrics it does not report are not shown. */
export function healthMetricsFor(agent: AgentTemplate | undefined): HealthMetric[] {
  return (agent?.reported_metrics ?? []).map(
    (key) => HEALTH[key] ?? { key, label: key.replace(/_/g, ' '), hint: '' },
  )
}

export function healthLabel(key: string): string {
  return HEALTH[key]?.label ?? key.replace(/_/g, ' ')
}
