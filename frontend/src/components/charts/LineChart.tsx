export interface ChartPoint {
  x: number
  y: number
}

export type LineStyle = 'solid' | 'dashed' | 'dotted'

export interface ChartSeries {
  id: string
  label: string
  points: ChartPoint[]
  lineStyle: LineStyle
  emphasis?: boolean
}

export interface ChartMarker {
  x: number
  label: string
}

export interface LineChartProps {
  series: ChartSeries[]
  markers?: ChartMarker[]
  xLabel: string
  yLabel: string
  height?: number
  title: string
}

const PADDING = { top: 16, right: 16, bottom: 34, left: 52 }

const dashArray: Record<LineStyle, string | undefined> = {
  solid: undefined,
  dashed: '6 4',
  dotted: '2 3',
}

function niceTicks(min: number, max: number, count: number): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    return [min]
  }
  const step = (max - min) / (count - 1)
  return Array.from({ length: count }, (_, i) => min + step * i)
}

function formatTick(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${(value / 1_000).toFixed(abs >= 10_000 ? 0 : 1)}k`
  if (abs >= 10) return value.toFixed(0)
  return value.toFixed(abs < 1 ? 2 : 1)
}

export function LineChart({
  series,
  markers = [],
  xLabel,
  yLabel,
  height = 340,
  title,
}: LineChartProps) {
  const allPoints = series.flatMap((s) => s.points)
  const width = 760

  if (allPoints.length === 0) {
    return (
      <div
        role="img"
        aria-label={`${title}: no data recorded`}
        style={{
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: '1px dashed var(--border-primary)',
          borderRadius: 'var(--radius-md)',
          color: 'var(--text-muted)',
          fontSize: 'var(--text-sm)',
          fontFamily: 'var(--font-sans)',
        }}
      >
        No recorded data for this chart
      </div>
    )
  }

  const xs = allPoints.map((p) => p.x)
  const ys = allPoints.map((p) => p.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys, 0)
  const maxY = Math.max(...ys)

  const plotWidth = width - PADDING.left - PADDING.right
  const plotHeight = height - PADDING.top - PADDING.bottom

  const scaleX = (x: number) => {
    if (maxX === minX) return PADDING.left + plotWidth / 2
    return PADDING.left + ((x - minX) / (maxX - minX)) * plotWidth
  }
  const scaleY = (y: number) => {
    if (maxY === minY) return PADDING.top + plotHeight / 2
    return PADDING.top + plotHeight - ((y - minY) / (maxY - minY)) * plotHeight
  }

  const xTicks = niceTicks(minX, maxX, 6)
  const yTicks = niceTicks(minY, maxY, 5)

  return (
    <figure style={{ margin: 0, fontFamily: 'var(--font-sans)' }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label={`${title}. ${series.map((s) => `${s.label}: ${s.points.length} points`).join('. ')}`}
        style={{ display: 'block', overflow: 'visible' }}
      >
        {yTicks.map((tick) => (
          <g key={`y-${tick}`}>
            <line
              x1={PADDING.left}
              x2={width - PADDING.right}
              y1={scaleY(tick)}
              y2={scaleY(tick)}
              stroke="var(--border-secondary)"
              strokeWidth={1}
            />
            <text
              x={PADDING.left - 8}
              y={scaleY(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              fill="var(--text-muted)"
              fontSize={11}
            >
              {formatTick(tick)}
            </text>
          </g>
        ))}

        {xTicks.map((tick) => (
          <text
            key={`x-${tick}`}
            x={scaleX(tick)}
            y={height - 12}
            textAnchor="middle"
            fill="var(--text-muted)"
            fontSize={11}
          >
            {formatTick(tick)}
          </text>
        ))}

        {markers.map((marker) => (
          <g key={`marker-${marker.label}-${marker.x}`}>
            <line
              x1={scaleX(marker.x)}
              x2={scaleX(marker.x)}
              y1={PADDING.top}
              y2={PADDING.top + plotHeight}
              stroke="var(--text-muted)"
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            <text
              x={scaleX(marker.x) + 4}
              y={PADDING.top + 10}
              fill="var(--text-muted)"
              fontSize={10}
            >
              {marker.label}
            </text>
          </g>
        ))}

        {series.map((s) => {
          const path = s.points
            .slice()
            .sort((a, b) => a.x - b.x)
            .map(
              (p, i) => `${i === 0 ? 'M' : 'L'}${scaleX(p.x).toFixed(2)},${scaleY(p.y).toFixed(2)}`,
            )
            .join(' ')
          return (
            <path
              key={s.id}
              d={path}
              fill="none"
              stroke={s.emphasis ? 'var(--text-primary)' : 'var(--text-secondary)'}
              strokeWidth={s.emphasis ? 2 : 1.5}
              strokeDasharray={dashArray[s.lineStyle]}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          )
        })}

        <line
          x1={PADDING.left}
          x2={width - PADDING.right}
          y1={PADDING.top + plotHeight}
          y2={PADDING.top + plotHeight}
          stroke="var(--border-primary)"
          strokeWidth={1}
        />
        <line
          x1={PADDING.left}
          x2={PADDING.left}
          y1={PADDING.top}
          y2={PADDING.top + plotHeight}
          stroke="var(--border-primary)"
          strokeWidth={1}
        />

        <text
          x={PADDING.left + plotWidth / 2}
          y={height - 1}
          textAnchor="middle"
          fill="var(--text-secondary)"
          fontSize={11}
        >
          {xLabel}
        </text>
        <text
          x={12}
          y={PADDING.top + plotHeight / 2}
          textAnchor="middle"
          fill="var(--text-secondary)"
          fontSize={11}
          transform={`rotate(-90 12 ${PADDING.top + plotHeight / 2})`}
        >
          {yLabel}
        </text>
      </svg>

      <figcaption
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 'var(--space-4)',
          marginTop: 'var(--space-3)',
          fontSize: 'var(--text-xs)',
          color: 'var(--text-secondary)',
        }}
      >
        {series.map((s) => (
          <span
            key={s.id}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)' }}
          >
            <svg width="24" height="8" aria-hidden="true">
              <line
                x1="0"
                y1="4"
                x2="24"
                y2="4"
                stroke={s.emphasis ? 'var(--text-primary)' : 'var(--text-secondary)'}
                strokeWidth={s.emphasis ? 2 : 1.5}
                strokeDasharray={dashArray[s.lineStyle]}
              />
            </svg>
            {s.label}
          </span>
        ))}
      </figcaption>
    </figure>
  )
}
