import { useEffect, useMemo, useState } from 'react'
import type { ChartSeries } from '../../components/charts/LineChart'
import type { LiveStatRow } from '../monitoring/LiveStatsPanel'
import {
  createTrainingHistoryService,
  type RunMetrics,
  type TrainingHistoryService,
} from '../../services/trainingHistory'

const POLL_MS = 3000

export interface RunMetricsState {
  status: 'idle' | 'loading' | 'ready' | 'error'
  metrics: RunMetrics | null
}

/**
 * The selected run's persisted metrics. A finished, stopped, failed or interrupted run is read once from history;
 * only a run that is still active is re-read on an interval, so historical pages never poll.
 */
export function useRunMetrics(
  projectId: string | null,
  runId: string | null,
  active: boolean,
  service?: TrainingHistoryService,
): RunMetricsState {
  const api = useMemo(() => service ?? createTrainingHistoryService(), [service])
  const [state, setState] = useState<RunMetricsState>({ status: 'idle', metrics: null })

  useEffect(() => {
    if (projectId === null || runId === null) {
      setState({ status: 'idle', metrics: null })
      return
    }
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    async function load(first: boolean) {
      const result = await api.getMetrics(
        projectId as string,
        runId as string,
        200,
        controller.signal,
      )
      if (controller.signal.aborted) return
      if (result.state === 'ok') setState({ status: 'ready', metrics: result.data })
      else setState((cur) => ({ status: 'error', metrics: first ? null : cur.metrics }))
      if (active && !controller.signal.aborted) timer = setTimeout(() => void load(false), POLL_MS)
    }
    setState({ status: 'loading', metrics: null }) // never show the previous run's numbers while this one loads
    void load(true)
    return () => {
      controller.abort()
      if (timer !== undefined) clearTimeout(timer)
    }
  }, [api, projectId, runId, active])

  return state
}

function fixed(value: number | null | undefined, digits: number): string | null {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : null
}

/** Stat rows for the Monitoring "Live Stats" panel. A value the run did not record stays `null` (never 0). */
export function metricRows(
  metrics: RunMetrics | null,
  durationSeconds: number | null,
): LiveStatRow[] {
  const final = metrics?.final_metrics ?? {}
  const success = final.success_rate
  return [
    {
      id: 'episode',
      label: 'Episode',
      kind: 'episode',
      value: metrics === null ? null : String(metrics.total_episodes ?? metrics.episodes_total),
    },
    {
      id: 'total-steps',
      label: 'Total Steps',
      kind: 'steps',
      value: metrics?.total_timesteps == null ? null : String(metrics.total_timesteps),
    },
    {
      id: 'avg-reward',
      label: 'Average Reward',
      kind: 'reward',
      value: fixed(final.mean_reward, 2),
    },
    {
      id: 'success-rate',
      label: 'Success Rate',
      kind: 'success',
      value: typeof success === 'number' ? fixed(success * 100, 1) : null,
      unit: '%',
    },
    {
      id: 'training-time',
      label: 'Training Time',
      kind: 'time',
      value: fixed(durationSeconds, 1),
      unit: 's',
    },
  ]
}

/** Episode reward against training step, from the run's recorded episodes only. */
export function rewardSeries(metrics: RunMetrics | null, label: string): ChartSeries[] {
  if (metrics === null) return []
  const points = metrics.episodes
    .map((e, i) => ({ x: Number(e.end_step ?? e.episode ?? i + 1), y: e.reward }))
    .filter((p): p is { x: number; y: number } => typeof p.y === 'number' && Number.isFinite(p.x))
  return points.length === 0
    ? []
    : [{ id: 'reward', label, points, lineStyle: 'solid', emphasis: true }]
}
