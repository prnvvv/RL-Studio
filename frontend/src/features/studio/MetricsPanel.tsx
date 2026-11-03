import { useMemo } from 'react'
import { LineChart, type ChartSeries } from '../../components/charts/LineChart'
import { findBestEpisode } from './bestEpisode'
import { downsample, formatDuration, formatInt, formatNumber, formatPercent } from './format'
import { ChartCard, MetricSection } from './metrics/ChartCard'
import { EnvironmentProgress } from './metrics/EnvironmentProgress'
import { LengthHistogram, TerminationBreakdown } from './metrics/EpisodeStats'
import { HealthCharts } from './metrics/HealthCharts'
import { healthLabel, lastN } from './metrics/metricData'
import { useRange } from './metrics/useRange'
import type { StudioState, StudioStore } from './studioStore'
import type { AgentTemplate, EpisodeRecord, EvaluationRecord, UpdateRecord } from './studioTypes'

const MAX_POINTS = 300
/** The chart drawing is 420 units wide so its text stays legible in the metrics column. */
const CHART_WIDTH = 420
const CHART_HEIGHT = 160

interface Props {
  state: StudioState
  agent: AgentTemplate | undefined
  /** Live frame source; enables the current-episode readouts under "Environment dynamics". */
  store?: StudioStore
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

/** Training reward, with the deterministic evaluation reward overlaid as a separate dashed line. */
function RewardChart({
  episodes,
  evaluations,
  total,
  bestEpisode,
}: {
  episodes: EpisodeRecord[]
  evaluations: EvaluationRecord[]
  total: number
  bestEpisode: EpisodeRecord | null
}) {
  const { range, control } = useRange()
  const visible = useMemo(() => lastN(episodes, range), [episodes, range])
  const from = range === 'all' || visible.length === 0 ? -Infinity : visible[0].timestep
  const series = useMemo<ChartSeries[]>(() => {
    const sampled = downsample(visible, MAX_POINTS)
    const out: ChartSeries[] = [
      {
        id: 'reward',
        label: 'Episode reward',
        lineStyle: 'dotted',
        points: sampled.map((e) => ({ x: e.timestep, y: e.reward })),
      },
      {
        id: 'avg',
        label: 'Moving average (20)',
        lineStyle: 'solid',
        emphasis: true,
        points: sampled.map((e) => ({ x: e.timestep, y: e.moving_avg_reward })),
      },
    ]
    const evalPoints = evaluations
      .filter((e) => e.timestep >= from)
      .map((e) => ({ x: e.timestep, y: e.mean_reward }))
    if (evalPoints.length > 0) {
      out.push({
        id: 'eval',
        label: 'Evaluation reward (deterministic)',
        lineStyle: 'dashed',
        emphasis: true,
        points: evalPoints,
      })
    }
    return out
  }, [visible, evaluations, from])
  return (
    <ChartCard
      title="Reward vs. timestep"
      hint="Dotted: each training episode. Solid: moving average. Dashed: deterministic evaluation rollouts in a separate environment. If the dashed line falls behind the solid one, the policy may be overfitting to training conditions."
      control={control}
    >
      <LineChart
        title="Episode reward versus timestep"
        series={series}
        xLabel="Timestep"
        yLabel="Reward"
        height={CHART_HEIGHT}
        width={CHART_WIDTH}
        responsive
        xDomain={[0, total]}
        markers={bestEpisode ? [{ x: bestEpisode.timestep, label: 'best' }] : []}
        emptyMessage="Waiting for the first episode"
      />
    </ChartCard>
  )
}

function SuccessChart({ episodes, total }: { episodes: EpisodeRecord[]; total: number }) {
  const { range, control } = useRange()
  const series = useMemo<ChartSeries[]>(
    () => [
      {
        id: 'success',
        label: 'Success rate (last 50)',
        lineStyle: 'solid',
        emphasis: true,
        points: downsample(lastN(episodes, range), MAX_POINTS).map((e) => ({
          x: e.timestep,
          y: e.success_rate,
        })),
      },
    ],
    [episodes, range],
  )
  return (
    <ChartCard title="Success rate" control={control}>
      <LineChart
        title="Success rate versus timestep"
        series={series}
        xLabel="Timestep"
        yLabel="Rate"
        height={CHART_HEIGHT}
        width={CHART_WIDTH}
        responsive
        xDomain={[0, total]}
        yDomain={[0, 1]}
        emptyMessage="Waiting for the first episode"
      />
    </ChartCard>
  )
}

function EvaluationChart({ evaluations }: { evaluations: EvaluationRecord[] }) {
  const { range, control } = useRange()
  const series = useMemo<ChartSeries[]>(
    () => [
      {
        id: 'eval',
        label: 'Evaluation mean reward',
        lineStyle: 'solid',
        emphasis: true,
        points: lastN(evaluations, range).map((e) => ({ x: e.timestep, y: e.mean_reward })),
      },
    ],
    [evaluations, range],
  )
  const last = evaluations[evaluations.length - 1]
  return (
    <ChartCard
      title="Evaluation (deterministic policy, separate env)"
      value={last ? `success ${formatPercent(last.success_rate)}` : null}
      control={control}
    >
      <LineChart
        title="Evaluation reward versus timestep"
        series={series}
        xLabel="Timestep"
        yLabel="Mean reward"
        height={CHART_HEIGHT}
        width={CHART_WIDTH}
        responsive
      />
    </ChartCard>
  )
}

/** Live training analytics. Every number comes from backend events; none are synthesized. */
export function MetricsPanel({ state, agent, store }: Props) {
  const { progress, episodes, updates, evaluations } = state

  if (!progress) {
    return <div className="empty">No session. Initialize an environment to see live metrics.</div>
  }

  // Only metrics this algorithm reports, and only once at least one value exists.
  const reported = (agent?.reported_metrics ?? []).filter((key) =>
    updates.some((u) => typeof u[key as keyof UpdateRecord] === 'number'),
  )
  const lastEval = evaluations[evaluations.length - 1]
  const total = Math.max(progress.total_timesteps, 1)
  // The backend's best_reward is authoritative; the episode list may have dropped old entries.
  const candidate = findBestEpisode(episodes)
  const bestEpisode =
    candidate !== null && candidate.reward === progress.best_reward ? candidate : null
  const maxSteps = Number(state.config?.env_params?.max_episode_steps)

  return (
    <div className="metrics-panel">
      <MetricSection title="Training progress">
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
          {Object.entries(progress.env_state ?? {})
            .filter(([, value]) => typeof value === 'number')
            .map(([key, value]) => (
              <Tile
                key={key}
                label={`Env ${key.replace(/_/g, ' ')}`}
                value={formatNumber(value, 3)}
              />
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
              label={healthLabel(key)}
              value={formatNumber(latest(updates, key as keyof UpdateRecord), 3)}
            />
          ))}
        </div>
        {progress.best_reward !== null && (
          <div className="best-episode" role="status" data-testid="best-episode">
            <strong>Best episode</strong>{' '}
            {bestEpisode
              ? `#${bestEpisode.episode} — reward ${formatNumber(bestEpisode.reward)} over ${formatInt(bestEpisode.length)} steps (timestep ${formatInt(bestEpisode.timestep)}, ${bestEpisode.reason.replace(/_/g, ' ')})`
              : `reward ${formatNumber(progress.best_reward)} (an earlier episode no longer kept in this view)`}
          </div>
        )}
        <div className="chart-stack">
          <RewardChart
            episodes={episodes}
            evaluations={evaluations}
            total={total}
            bestEpisode={bestEpisode}
          />
          <SuccessChart episodes={episodes} total={total} />
          {evaluations.length > 0 && <EvaluationChart evaluations={evaluations} />}
        </div>
      </MetricSection>

      <MetricSection title="Algorithm health">
        <HealthCharts agent={agent} updates={updates} total={total} />
      </MetricSection>

      <MetricSection title="Episode statistics">
        <div className="chart-stack">
          <LengthHistogram
            episodes={episodes}
            maxSteps={Number.isFinite(maxSteps) ? maxSteps : null}
          />
          <TerminationBreakdown episodes={episodes} />
        </div>
      </MetricSection>

      <MetricSection title="Environment dynamics">
        {store ? (
          <EnvironmentProgress
            store={store}
            progress={progress}
            maxSteps={Number.isFinite(maxSteps) ? maxSteps : null}
          />
        ) : (
          <p className="note">Live episode readouts need a connected session.</p>
        )}
      </MetricSection>
    </div>
  )
}
