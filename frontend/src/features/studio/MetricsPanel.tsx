import { useMemo } from 'react'
import { LineChart, type ChartSeries } from '../../components/charts/LineChart'
import { downsample, formatDuration, formatInt, formatNumber, formatPercent } from './format'
import type { StudioState } from './studioStore'
import type { AgentTemplate, UpdateRecord } from './studioTypes'

const MAX_POINTS = 300
const CHART_HEIGHT = 190

const METRIC_LABELS: Record<string, string> = {
  policy_loss: 'Policy loss',
  value_loss: 'Value loss',
  entropy: 'Entropy',
  approx_kl: 'Approx. KL',
  explained_variance: 'Explained variance',
  clip_fraction: 'Clip fraction',
  loss: 'Loss',
  exploration_rate: 'Exploration rate',
}

interface Props {
  state: StudioState
  agent: AgentTemplate | undefined
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="tile">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function latest(updates: UpdateRecord[], key: keyof UpdateRecord): number | null {
  for (let i = updates.length - 1; i >= 0; i -= 1) {
    const value = updates[i][key]
    if (typeof value === 'number') return value
  }
  return null
}

/** Live training analytics. Every number comes from backend events; none are synthesized. */
export function MetricsPanel({ state, agent }: Props) {
  const { progress, episodes, updates, evaluations } = state

  const rewardSeries = useMemo<ChartSeries[]>(
    () => [
      {
        id: 'reward',
        label: 'Episode reward',
        lineStyle: 'dotted',
        points: downsample(episodes, MAX_POINTS).map((e) => ({ x: e.timestep, y: e.reward })),
      },
      {
        id: 'avg',
        label: 'Moving average (20)',
        lineStyle: 'solid',
        emphasis: true,
        points: downsample(episodes, MAX_POINTS).map((e) => ({
          x: e.timestep,
          y: e.moving_avg_reward,
        })),
      },
    ],
    [episodes],
  )

  const successSeries = useMemo<ChartSeries[]>(
    () => [
      {
        id: 'success',
        label: 'Success rate (last 50)',
        lineStyle: 'solid',
        emphasis: true,
        points: downsample(episodes, MAX_POINTS).map((e) => ({ x: e.timestep, y: e.success_rate })),
      },
    ],
    [episodes],
  )

  // Only metrics this algorithm reports, and only once at least one value exists.
  const reported = (agent?.reported_metrics ?? []).filter((key) =>
    updates.some((u) => typeof u[key as keyof UpdateRecord] === 'number'),
  )
  const lossSeries = useMemo<ChartSeries[]>(
    () =>
      reported
        .filter((key) => ['policy_loss', 'value_loss', 'loss'].includes(key))
        .map((key, index) => ({
          id: key,
          label: METRIC_LABELS[key] ?? key,
          lineStyle: (index === 0 ? 'solid' : 'dashed') as ChartSeries['lineStyle'],
          points: downsample(updates, MAX_POINTS)
            .filter((u) => typeof u[key as keyof UpdateRecord] === 'number')
            .map((u) => ({ x: u.timestep, y: u[key as keyof UpdateRecord] as number })),
        })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [updates, agent?.key],
  )
  const evalSeries = useMemo<ChartSeries[]>(
    () => [
      {
        id: 'eval',
        label: 'Evaluation mean reward',
        lineStyle: 'solid',
        emphasis: true,
        points: evaluations.map((e) => ({ x: e.timestep, y: e.mean_reward })),
      },
    ],
    [evaluations],
  )

  if (!progress) {
    return <div className="empty">No session. Initialize an environment to see live metrics.</div>
  }

  const lastEval = evaluations[evaluations.length - 1]

  return (
    <div>
      <div
        className="progress-bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(progress.fraction * 100)}
        aria-label="Training progress"
      >
        <div style={{ width: `${progress.fraction * 100}%` }} />
      </div>
      <div className="tiles">
        <Tile
          label="Timestep"
          value={`${formatInt(progress.timestep)} / ${formatInt(progress.total_timesteps)}`}
        />
        <Tile label="Episodes" value={formatInt(progress.episodes)} />
        <Tile label="Duration" value={formatDuration(progress.elapsed_seconds)} />
        <Tile label="Steps / sec" value={formatInt(progress.steps_per_second)} />
        <Tile label="Moving avg reward" value={formatNumber(progress.current_reward_avg)} />
        <Tile label="Mean reward" value={formatNumber(progress.mean_reward)} />
        <Tile label="Best reward" value={formatNumber(progress.best_reward)} />
        <Tile label="Success rate" value={formatPercent(progress.success_rate)} />
        <Tile label="Collisions" value={formatInt(progress.collisions)} />
        <Tile
          label="Last termination"
          value={progress.last_termination?.replace(/_/g, ' ') ?? '—'}
        />
        {Object.entries(progress.env_state ?? {}).map(([key, value]) => (
          <Tile key={key} label={`Env ${key.replace(/_/g, ' ')}`} value={formatNumber(value, 3)} />
        ))}
        {lastEval && (
          <Tile
            label="Eval reward"
            value={`${formatNumber(lastEval.mean_reward)} ± ${formatNumber(lastEval.std_reward)}`}
          />
        )}
        {reported.map((key) => (
          <Tile
            key={key}
            label={METRIC_LABELS[key] ?? key}
            value={formatNumber(latest(updates, key as keyof UpdateRecord), 3)}
          />
        ))}
      </div>
      <div className="charts">
        <div className="chart-card">
          <h4>Reward vs. timestep</h4>
          <LineChart
            title="Episode reward versus timestep"
            series={rewardSeries}
            xLabel="Timestep"
            yLabel="Reward"
            height={CHART_HEIGHT}
          />
        </div>
        <div className="chart-card">
          <h4>Success rate</h4>
          <LineChart
            title="Success rate versus timestep"
            series={successSeries}
            xLabel="Timestep"
            yLabel="Rate"
            height={CHART_HEIGHT}
          />
        </div>
        {lossSeries.length > 0 && (
          <div className="chart-card">
            <h4>Algorithm loss</h4>
            <LineChart
              title="Loss versus timestep"
              series={lossSeries}
              xLabel="Timestep"
              yLabel="Loss"
              height={CHART_HEIGHT}
            />
          </div>
        )}
        {evaluations.length > 0 && (
          <div className="chart-card">
            <h4>Evaluation (deterministic policy, separate env)</h4>
            <LineChart
              title="Evaluation reward versus timestep"
              series={evalSeries}
              xLabel="Timestep"
              yLabel="Mean reward"
              height={CHART_HEIGHT}
            />
          </div>
        )}
      </div>
    </div>
  )
}
