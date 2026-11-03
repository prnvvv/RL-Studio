import { useMemo } from 'react'
import { LineChart, type ChartSeries } from '../../components/charts/LineChart'
import { comparisonRows, leaderOf } from './battle'
import { downsample } from './format'
import type { StudioState } from './studioStore'

const MAX_POINTS = 300

interface Props {
  stateA: StudioState
  stateB: StudioState
}

/** Live side-by-side numbers and an overlaid reward curve. Everything comes from each session's own events. */
export function CompareMetrics({ stateA, stateB }: Props) {
  const rows = comparisonRows(stateA.progress, stateB.progress)
  const leader = leaderOf(stateA.progress, stateB.progress)
  const series = useMemo<ChartSeries[]>(
    () => [
      {
        id: 'a',
        label: `A · ${stateA.config?.agent ?? ''} moving average`,
        lineStyle: 'solid',
        emphasis: true,
        points: downsample(stateA.episodes, MAX_POINTS).map((e) => ({
          x: e.timestep,
          y: e.moving_avg_reward,
        })),
      },
      {
        id: 'b',
        label: `B · ${stateB.config?.agent ?? ''} moving average`,
        lineStyle: 'dashed',
        points: downsample(stateB.episodes, MAX_POINTS).map((e) => ({
          x: e.timestep,
          y: e.moving_avg_reward,
        })),
      },
    ],
    [stateA.episodes, stateA.config?.agent, stateB.episodes, stateB.config?.agent],
  )
  const total = Math.max(stateA.progress?.total_timesteps ?? 1, 1)

  return (
    <div>
      <table className="mini-table compare-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th>A · {stateA.config?.agent ?? '—'}</th>
            <th>B · {stateB.config?.agent ?? '—'}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.label}
              data-leader={row.label === 'Moving avg reward' ? (leader ?? undefined) : undefined}
            >
              <th scope="row">{row.label}</th>
              <td>{row.a}</td>
              <td>{row.b}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="note">
        {leader
          ? `Side ${leader.toUpperCase()} has the higher moving-average reward right now. This is a snapshot of one seeded run each, not a significance test.`
          : 'No leader yet: both sides need to finish an episode, and a tie is not a lead.'}
      </p>
      <LineChart
        title="Moving average reward, side A versus side B"
        series={series}
        xLabel="Timestep"
        yLabel="Reward"
        height={190}
        xDomain={[0, total]}
        emptyMessage="Waiting for the first episodes"
      />
    </div>
  )
}
