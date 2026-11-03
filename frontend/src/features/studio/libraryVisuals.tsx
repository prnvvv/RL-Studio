import type { ReactNode } from 'react'
import type { GridLayout } from './studioTypes'

/**
 * Small monochrome SVG illustrations for the Agents & Environments library.
 * Everything here is decorative and draws with `currentColor`, so it follows the theme.
 * The curves are NOT training data; they only hint at each algorithm's character.
 */

const STROKE = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
} as const

function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      {...STROKE}
    >
      {children}
    </svg>
  )
}

export function LayersIcon({ size }: { size?: number }) {
  return (
    <Icon size={size}>
      <path d="M12 3 21 8l-9 5-9-5 9-5Z" />
      <path d="m3 12 9 5 9-5" />
      <path d="m3 16 9 5 9-5" />
    </Icon>
  )
}

export function CubeIcon({ size }: { size?: number }) {
  return (
    <Icon size={size}>
      <path d="m12 2.5 8.5 4.75v9.5L12 21.5l-8.5-4.75v-9.5L12 2.5Z" />
      <path d="m3.5 7.25 8.5 4.75 8.5-4.75M12 12v9.5" />
    </Icon>
  )
}

export function UploadCloudIcon({ size = 26 }: { size?: number }) {
  return (
    <Icon size={size}>
      <path d="M7 18a4.5 4.5 0 0 1-.6-8.96A6 6 0 0 1 17.9 8.5 3.75 3.75 0 0 1 17.5 18H7Z" />
      <path d="M12 16v-6m-2.5 2.5L12 10l2.5 2.5" />
    </Icon>
  )
}

/** PPO: a policy waveform. A2C: stacked layers. DQN: a small network. */
export function AgentIcon({ agentKey }: { agentKey: string }) {
  if (agentKey === 'PPO') {
    return (
      <Icon>
        <path d="M2.5 12c1.6-6 3.2-6 4.8 0s3.2 6 4.8 0 3.2-6 4.8 0 2.4 4.5 3.6 3" />
      </Icon>
    )
  }
  if (agentKey === 'A2C') return <LayersIcon />
  if (agentKey === 'DQN') {
    return (
      <Icon>
        <circle cx="12" cy="12" r="9" />
        <circle cx="12" cy="12" r="2.5" />
        <path d="M12 3v6.5M12 14.5V21M3.4 8.5l6.5 3M14.1 12.5l6.5 3M3.4 15.5l6.5-3M14.1 11.5l6.5-3" />
      </Icon>
    )
  }
  // Uploaded or unknown models: a neutral "model" glyph.
  return (
    <Icon>
      <rect x="4" y="4" width="16" height="16" rx="3" />
      <path d="M9 9h6v6H9zM4 9H2m2 6H2m20-6h-2m2 6h-2M9 4V2m6 2V2M9 22v-2m6 2v-2" />
    </Icon>
  )
}

export function CheckBadge() {
  return (
    <span className="check-badge" aria-hidden="true">
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path
          d="m2.5 6.4 2.3 2.3 4.7-5"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  )
}

/** The RL Studio mark: a policy curve rising through a square frame. */
export function LogoMark({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      {...STROKE}
    >
      <rect x="3" y="3" width="18" height="18" rx="4" />
      <path d="M7 16.5c2.2 0 2.6-5 5-5s2.2-3 5-3" />
      <circle cx="17" cy="8.5" r="1" fill="currentColor" stroke="none" />
    </svg>
  )
}

// ---------------------------------------------------------------- mini graphs

const GRAPH_W = 165
const GRAPH_H = 55

const GRAPH_PATHS: Record<string, string> = {
  // Smooth, converging curve.
  PPO: 'M2 47C26 46 46 40 70 26S128 8 163 6',
  // Rising with slight fluctuations.
  A2C: 'M2 47 17 43 30 45 44 36 60 38 74 28 90 31 106 20 122 23 140 12 152 14 163 7',
  // Stepped progression.
  DQN: 'M2 49H24V41H50V34H72V27H100V20H126V12H152V7H163',
}

/** A decorative learning-curve sketch with a faint grid. Not real metrics. */
export function AgentGraph({ agentKey }: { agentKey: string }) {
  const path = GRAPH_PATHS[agentKey]
  if (!path) return null
  return (
    <svg
      className="agent-graph"
      viewBox={`0 0 ${GRAPH_W} ${GRAPH_H}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <g
        stroke="currentColor"
        strokeOpacity="0.1"
        strokeWidth="1"
        vectorEffect="non-scaling-stroke"
      >
        {[14, 28, 42].map((y) => (
          <line key={y} x1="0" x2={GRAPH_W} y1={y} y2={y} vectorEffect="non-scaling-stroke" />
        ))}
        {[41, 82, 124].map((x) => (
          <line key={x} x1={x} x2={x} y1="0" y2={GRAPH_H} vectorEffect="non-scaling-stroke" />
        ))}
      </g>
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

// ---------------------------------------------------------------- environment previews

const PREVIEW_W = 135
const PREVIEW_H = 78

function PreviewFrame({ children }: { children: ReactNode }) {
  return (
    <svg
      className="env-preview"
      viewBox={`0 0 ${PREVIEW_W} ${PREVIEW_H}`}
      aria-hidden="true"
      focusable="false"
    >
      <g stroke="currentColor" strokeOpacity="0.07" strokeWidth="1">
        {[13, 26, 39, 52, 65].map((y) => (
          <line key={y} x1="0" x2={PREVIEW_W} y1={y} y2={y} />
        ))}
        {[22, 45, 67, 90, 112].map((x) => (
          <line key={x} x1={x} x2={x} y1="0" y2={PREVIEW_H} />
        ))}
      </g>
      {children}
    </svg>
  )
}

function CartPolePreview() {
  return (
    <PreviewFrame>
      <line x1="8" x2="127" y1="58" y2="58" stroke="currentColor" strokeOpacity="0.5" />
      <rect
        x="48"
        y="46"
        width="38"
        height="12"
        rx="2"
        fill="currentColor"
        fillOpacity="0.08"
        stroke="currentColor"
        strokeWidth="1.4"
      />
      <circle cx="56" cy="60" r="3" fill="none" stroke="currentColor" strokeOpacity="0.7" />
      <circle cx="78" cy="60" r="3" fill="none" stroke="currentColor" strokeOpacity="0.7" />
      <line
        x1="67"
        x2="73"
        y1="46"
        y2="12"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <circle cx="67" cy="46" r="2" fill="currentColor" />
      <circle cx="73" cy="12" r="2.6" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </PreviewFrame>
  )
}

/** One isometric cube whose top-left corner of the top face is at (x, y). */
function Cube({ x, y, s, tone }: { x: number; y: number; s: number; tone: number }) {
  const w = s
  const h = s * 0.5
  const d = s * 0.9
  return (
    <g stroke="currentColor" strokeWidth="1" strokeLinejoin="round">
      <polygon
        points={`${x},${y} ${x + w},${y + h} ${x},${y + 2 * h} ${x - w},${y + h}`}
        fill="currentColor"
        fillOpacity={0.5 * tone}
      />
      <polygon
        points={`${x - w},${y + h} ${x},${y + 2 * h} ${x},${y + 2 * h + d} ${x - w},${y + h + d}`}
        fill="currentColor"
        fillOpacity={0.18 * tone}
      />
      <polygon
        points={`${x},${y + 2 * h} ${x + w},${y + h} ${x + w},${y + h + d} ${x},${y + 2 * h + d}`}
        fill="currentColor"
        fillOpacity={0.3 * tone}
      />
    </g>
  )
}

function WarehousePreview() {
  return (
    <PreviewFrame>
      {/* Perspective floor */}
      <g stroke="currentColor" strokeOpacity="0.28" strokeWidth="1" fill="none">
        <polygon points="67,18 125,44 67,70 9,44" />
        <path d="M38,31 96,57M52,24.5 110,50.5M82,24.5 24,50.5M96,31 38,57" />
      </g>
      <ellipse cx="46" cy="58" rx="10" ry="3" fill="currentColor" fillOpacity="0.1" />
      <ellipse cx="92" cy="46" rx="9" ry="2.6" fill="currentColor" fillOpacity="0.1" />
      <Cube x={46} y={40} s={9} tone={1} />
      <Cube x={92} y={30} s={8} tone={0.8} />
      <Cube x={68} y={46} s={6} tone={0.6} />
      <circle cx="104" cy="52" r="3.4" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="104" cy="52" r="1.2" fill="currentColor" />
    </PreviewFrame>
  )
}

/** Draws an uploaded grid exactly as it was declared: obstacles, start and goal. */
function GridPreview({ layout }: { layout: GridLayout }) {
  const cell = Math.min(122 / layout.cols, 68 / layout.rows)
  const width = cell * layout.cols
  const height = cell * layout.rows
  const ox = (PREVIEW_W - width) / 2
  const oy = (PREVIEW_H - height) / 2
  const at = ([r, c]: number[]) => ({ x: ox + c * cell, y: oy + r * cell })
  const start = layout.start.length === 2 ? at(layout.start) : null
  const goal = layout.goal.length === 2 ? at(layout.goal) : null
  return (
    <PreviewFrame>
      <rect
        x={ox}
        y={oy}
        width={width}
        height={height}
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.5"
      />
      <g stroke="currentColor" strokeOpacity="0.2">
        {Array.from({ length: layout.cols - 1 }, (_, i) => (
          <line
            key={`c${i}`}
            x1={ox + (i + 1) * cell}
            x2={ox + (i + 1) * cell}
            y1={oy}
            y2={oy + height}
          />
        ))}
        {Array.from({ length: layout.rows - 1 }, (_, i) => (
          <line
            key={`r${i}`}
            y1={oy + (i + 1) * cell}
            y2={oy + (i + 1) * cell}
            x1={ox}
            x2={ox + width}
          />
        ))}
      </g>
      {layout.obstacles.map((cellPos) => {
        const p = at(cellPos)
        return (
          <rect
            key={`${cellPos[0]},${cellPos[1]}`}
            x={p.x + 0.5}
            y={p.y + 0.5}
            width={cell - 1}
            height={cell - 1}
            fill="currentColor"
            fillOpacity="0.45"
          />
        )
      })}
      {start && (
        <circle
          cx={start.x + cell / 2}
          cy={start.y + cell / 2}
          r={cell * 0.28}
          fill="currentColor"
        />
      )}
      {goal && (
        <circle
          cx={goal.x + cell / 2}
          cy={goal.y + cell / 2}
          r={cell * 0.3}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
        />
      )}
    </PreviewFrame>
  )
}

export function EnvironmentPreview({
  envKey,
  renderer,
  layout,
}: {
  envKey: string
  renderer: string
  layout?: GridLayout
}) {
  if (layout) return <GridPreview layout={layout} />
  if (envKey === 'cartpole' || renderer === 'cartpole') return <CartPolePreview />
  if (envKey === 'warehouse' || renderer === 'warehouse') return <WarehousePreview />
  return <PreviewFrame>{null}</PreviewFrame>
}
