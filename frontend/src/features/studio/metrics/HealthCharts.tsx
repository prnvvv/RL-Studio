import { useMemo } from 'react'
import { LineChart, type ChartSeries } from '../../../components/charts/LineChart'
import { downsample, formatNumber } from '../format'
import type { AgentTemplate, UpdateRecord } from '../studioTypes'
import { ChartCard } from './ChartCard'
import { useRange } from './useRange'
import { healthMetricsFor, lastN, type HealthMetric } from './metricData'

const MAX_POINTS = 240

function valueOf(update: UpdateRecord, key: string): number | null {
  const value = (update as unknown as Record<string, unknown>)[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function HealthChart({
  metric,
  updates,
  total,
}: {
  metric: HealthMetric
  updates: UpdateRecord[]
  total: number
}) {
  const { range, control } = useRange()
  const withValue = useMemo(
    () => updates.filter((u) => valueOf(u, metric.key) !== null),
    [updates, metric.key],
  )
  const visible = useMemo(() => lastN(withValue, range), [withValue, range])
  const series = useMemo<ChartSeries[]>(
    () => [
      {
        id: metric.key,
        label: metric.label,
        lineStyle: 'solid',
        emphasis: true,
        points: downsample(visible, MAX_POINTS).map((u) => ({
          x: u.timestep,
          y: valueOf(u, metric.key) as number,
        })),
      },
    ],
    [visible, metric],
  )
  const latest = withValue.length > 0 ? valueOf(withValue[withValue.length - 1], metric.key) : null
  return (
    <ChartCard
      title={metric.label}
      hint={metric.hint}
      value={latest === null ? null : formatNumber(latest, 3)}
      control={control}
    >
      <LineChart
        title={`${metric.label} versus timestep`}
        series={series}
        xLabel="Timestep"
        yLabel={metric.label}
        height={140}
        width={420}
        responsive
        xDomain={[0, Math.max(total, 1)]}
        emptyMessage="Waiting for data"
      />
    </ChartCard>
  )
}

/**
 * Algorithm health: one chart for each statistic this algorithm really reports, read from SB3's
 * own logger. A chart that has not received its first value yet says so instead of staying hidden.
 */
export function HealthCharts({
  agent,
  updates,
  total,
}: {
  agent: AgentTemplate | undefined
  updates: UpdateRecord[]
  total: number
}) {
  const metrics = healthMetricsFor(agent)
  if (metrics.length === 0) {
    return <p className="note">This model reports no training statistics (inference only).</p>
  }
  return (
    <div className="chart-stack">
      {metrics.map((metric) => (
        <HealthChart key={metric.key} metric={metric} updates={updates} total={total} />
      ))}
    </div>
  )
}
