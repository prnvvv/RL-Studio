import { useFrameSnapshot } from '../useFrameSnapshot'
import { adaptCartPole, cartPoleActionDirection, cartPoleScene } from '../simulationAdapters'
import type { RendererProps } from './types'

/** Side view of the cart and pole, driven only by backend frame state. */
export function CartPole2D({ scene, store, palette }: RendererProps) {
  const frame = useFrameSnapshot(store)
  const dims = cartPoleScene(scene)
  const pose = adaptCartPole(frame, dims)
  const span = dims.x_limit + 0.8
  const push = cartPoleActionDirection(frame)
  const failed = frame?.done === true && frame.outcome?.success === false
  const poleColor = failed ? palette.bad : palette.agent

  return (
    <svg
      role="img"
      aria-label="CartPole side view"
      viewBox={`${-span} -1.6 ${span * 2} 2.4`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: '100%', height: '100%', background: palette.background }}
    >
      <line x1={-span} x2={span} y1={0.2} y2={0.2} stroke={palette.grid} strokeWidth={0.02} />
      {[-dims.x_limit, dims.x_limit].map((x) => (
        <line
          key={x}
          x1={x}
          x2={x}
          y1={0.2}
          y2={-0.5}
          stroke={palette.structure}
          strokeWidth={0.03}
        />
      ))}
      {push !== 0 && frame && (
        <polygon
          key={frame.timestep}
          className="action-flash"
          data-testid="action-arrow"
          points="0,-0.12 0.24,0 0,0.12"
          fill={palette.agent}
          transform={`translate(${pose.cartX + push * 0.5} 0) scale(${push} 1)`}
        />
      )}
      {frame?.brain?.probs?.length === 2 &&
        frame.brain.probs.map((p, side) => (
          <polygon
            key={`brain-${side}`}
            data-testid="brain-arrow"
            points="0,-0.1 0.2,0 0,0.1"
            fill={palette.accent}
            opacity={0.25 + 0.7 * p}
            transform={`translate(${pose.cartX + (side === 0 ? -1 : 1) * (0.55 + 0.25 * p)} 0.42) scale(${(side === 0 ? -1 : 1) * (0.5 + 2 * p)} 1)`}
          />
        ))}
      <g transform={`translate(${pose.cartX} 0)`}>
        <rect x={-0.25} y={-0.15} width={0.5} height={0.3} rx={0.03} fill={palette.accent} />
        <g transform={`translate(0 -0.15) rotate(${(pose.poleAngle * 180) / Math.PI})`}>
          <line
            x1={0}
            y1={0}
            x2={0}
            y2={-dims.pole_length}
            stroke={poleColor}
            strokeWidth={0.06}
            strokeLinecap="round"
          />
          <circle cx={0} cy={-dims.pole_length} r={0.07} fill={poleColor} />
        </g>
      </g>
    </svg>
  )
}
