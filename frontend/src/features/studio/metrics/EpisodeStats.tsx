import { useMemo } from 'react'
import { formatInt, formatNumber } from '../format'
import type { EpisodeRecord } from '../studioTypes'
import { ChartCard } from './ChartCard'
import { useRange } from './useRange'
import { countReasons, histogram, lastN } from './metricData'

const W = 420
const H = 150
const PAD = { top: 10, right: 8, bottom: 26, left: 34 }

/** Fill opacities that tell stacked segments apart without any colour. */
const SHADES = [1, 0.7, 0.5, 0.34, 0.22, 0.14]

/** Distribution of episode lengths: did episodes end early (failure) or run to the time limit? */
export function LengthHistogram({
  episodes,
  maxSteps,
}: {
  episodes: EpisodeRecord[]
  maxSteps: number | null
}) {
  const { range, control } = useRange()
  const visible = useMemo(() => lastN(episodes, range), [episodes, range])
  const lengths = useMemo(() => visible.map((e) => e.length), [visible])
  const bins = useMemo(() => histogram(lengths, 10), [lengths])
  const mean = lengths.length > 0 ? lengths.reduce((a, b) => a + b, 0) / lengths.length : null
  const peak = Math.max(1, ...bins.map((b) => b.count))
  const plotW = W - PAD.left - PAD.right
  const plotH = H - PAD.top - PAD.bottom
  const first = bins[0]?.from ?? 0
  const last = bins[bins.length - 1]?.to ?? 1
  const span = Math.max(last - first, 1)
  const limitX = maxSteps !== null && maxSteps >= first && maxSteps <= last

  return (
    <ChartCard
      title="Episode length"
      hint="How long episodes last. A pile-up at the time limit means the agent survives; a pile-up at the left means it fails early."
      value={mean === null ? null : `mean ${formatNumber(mean, 1)}`}
      control={control}
    >
      {bins.length === 0 ? (
        <div className="chart-empty" role="status" style={{ height: H }}>
          Waiting for data
        </div>
      ) : (
        <svg
          viewBox={`0 0 ${W} ${H}`}
          style={{ width: '100%', height: 'auto', display: 'block' }}
          role="img"
          aria-label={`Episode length histogram over ${formatInt(lengths.length)} episodes, from ${formatInt(first)} to ${formatInt(last)} steps`}
        >
          <line
            x1={PAD.left}
            x2={W - PAD.right}
            y1={PAD.top + plotH}
            y2={PAD.top + plotH}
            stroke="var(--border-primary)"
          />
          {bins.map((bin, index) => {
            const width = bins.length === 1 ? plotW * 0.4 : plotW / bins.length - 2
            const x =
              bins.length === 1
                ? PAD.left + plotW * 0.3
                : PAD.left + ((bin.from - first) / span) * plotW + 1
            const height = (bin.count / peak) * plotH
            return (
              <rect
                key={index}
                data-testid="length-bin"
                x={x}
                y={PAD.top + plotH - height}
                width={Math.max(width, 1)}
                height={height}
                fill="var(--text-primary)"
                fillOpacity={0.75}
              >
                <title>{`${formatInt(bin.from)}–${formatInt(bin.to)} steps: ${bin.count} episodes`}</title>
              </rect>
            )
          })}
          {limitX && (
            <g>
              <line
                x1={PAD.left + ((maxSteps - first) / span) * plotW}
                x2={PAD.left + ((maxSteps - first) / span) * plotW}
                y1={PAD.top}
                y2={PAD.top + plotH}
                stroke="var(--text-secondary)"
                strokeDasharray="4 3"
              />
            </g>
          )}
          <g fill="var(--text-muted)" fontSize="10">
            <text x={PAD.left} y={H - 8}>
              {formatInt(first)}
            </text>
            <text x={W - PAD.right} y={H - 8} textAnchor="end">
              {formatInt(last)} steps
            </text>
            <text x={PAD.left - 6} y={PAD.top + 8} textAnchor="end">
              {peak}
            </text>
            <text x={PAD.left - 6} y={PAD.top + plotH} textAnchor="end">
              0
            </text>
          </g>
        </svg>
      )}
    </ChartCard>
  )
}

/** Why episodes ended, as reported by the environment itself (its own reasons, not a fixed list). */
export function TerminationBreakdown({ episodes }: { episodes: EpisodeRecord[] }) {
  const { range, control } = useRange()
  const visible = useMemo(() => lastN(episodes, range), [episodes, range])
  const reasons = useMemo(() => countReasons(visible), [visible])
  return (
    <ChartCard
      title="Termination reasons"
      hint="The proportion of episodes ending for each reason the environment reports. It shows why the agent fails, not only that it does."
      value={visible.length > 0 ? `${formatInt(visible.length)} episodes` : null}
      control={control}
    >
      {reasons.length === 0 ? (
        <div className="chart-empty" role="status" style={{ height: 60 }}>
          Waiting for data
        </div>
      ) : (
        <>
          <div
            className="reason-bar"
            role="img"
            aria-label={`Termination reasons: ${reasons.map((r) => `${r.reason.replace(/_/g, ' ')} ${Math.round(r.share * 100)}%`).join(', ')}`}
          >
            {reasons.map((r, index) => (
              <span
                key={r.reason}
                data-testid="reason-segment"
                style={{
                  width: `${r.share * 100}%`,
                  opacity: SHADES[index % SHADES.length],
                }}
              />
            ))}
          </div>
          <ul className="reason-legend">
            {reasons.map((r, index) => (
              <li key={r.reason}>
                <i style={{ opacity: SHADES[index % SHADES.length] }} aria-hidden="true" />
                <span>{r.reason.replace(/_/g, ' ')}</span>
                <strong>
                  {formatInt(r.count)} · {Math.round(r.share * 100)}%
                </strong>
              </li>
            ))}
          </ul>
        </>
      )}
    </ChartCard>
  )
}
