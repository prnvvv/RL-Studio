import { useFrameSnapshot } from '../useFrameSnapshot'
import { stateNumber } from '../simulationAdapters'
import type { RendererProps } from './types'

interface HillScene {
  min: number
  max: number
  goal: number
}

function hillScene(scene: Record<string, unknown> | null): HillScene {
  const s = (scene ?? {}) as Record<string, unknown>
  const num = (key: string, fallback: number) =>
    typeof s[key] === 'number' ? (s[key] as number) : fallback
  return {
    min: num('min_position', -1.2),
    max: num('max_position', 0.6),
    goal: num('goal_position', 0.5),
  }
}

/** The hill's real height profile (the same curve Gymnasium's MountainCar simulates). */
const height = (x: number) => Math.sin(3 * x) * 0.45 + 0.55
const slope = (x: number) => Math.cos(3 * x) * 0.45 * 3

/** Side view of the car on the hill, driven only by backend frame state. */
export function MountainCar2D({ scene, store, palette }: RendererProps) {
  const frame = useFrameSnapshot(store)
  const hill = hillScene(scene)
  const position = stateNumber(frame, 'position', -0.5)
  const steps = 120
  const curve = Array.from({ length: steps + 1 }, (_, i) => {
    const x = hill.min + ((hill.max - hill.min) * i) / steps
    return `${x.toFixed(4)},${(-height(x)).toFixed(4)}`
  })
  const angle = (Math.atan(slope(position)) * 180) / Math.PI
  const push = typeof frame?.action === 'number' ? frame.action - 1 : 0 // 0 left, 1 coast, 2 right
  const reached = frame?.done === true && frame.outcome?.success === true
  const pad = 0.12

  return (
    <svg
      role="img"
      aria-label="MountainCar side view"
      viewBox={`${hill.min - pad} -1.3 ${hill.max - hill.min + pad * 2} 1.6`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: '100%', height: '100%', background: palette.background }}
    >
      <polygon
        points={`${hill.min},0.2 ${curve.join(' ')} ${hill.max},0.2`}
        fill={palette.floor}
        stroke={palette.structure}
        strokeWidth={0.015}
      />
      <g stroke={palette.grid} strokeWidth={0.006}>
        {[-0.8, -0.4, 0, 0.4].map((x) => (
          <line key={x} x1={x} x2={x} y1={-1.2} y2={0.2} />
        ))}
      </g>
      <g transform={`translate(${hill.goal} ${-height(hill.goal)})`}>
        <line y1={0} y2={-0.2} stroke={palette.agent} strokeWidth={0.012} />
        <polygon points="0,-0.2 0.1,-0.165 0,-0.13" fill={reached ? palette.good : palette.agent} />
      </g>
      <g transform={`translate(${position} ${-height(position)}) rotate(${-angle})`}>
        <rect x={-0.055} y={-0.075} width={0.11} height={0.045} rx={0.01} fill={palette.agent} />
        <circle
          cx={-0.032}
          cy={-0.026}
          r={0.017}
          fill={palette.background}
          stroke={palette.agent}
          strokeWidth={0.008}
        />
        <circle
          cx={0.032}
          cy={-0.026}
          r={0.017}
          fill={palette.background}
          stroke={palette.agent}
          strokeWidth={0.008}
        />
        {push !== 0 && (
          <polygon
            key={frame?.timestep}
            className="action-flash"
            data-testid="action-arrow"
            points="0,-0.03 0.07,0 0,0.03"
            fill={palette.accent}
            transform={`translate(${push * 0.12} -0.05) scale(${push} 1)`}
          />
        )}
      </g>
    </svg>
  )
}
