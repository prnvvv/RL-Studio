import { useFrameSnapshot } from '../useFrameSnapshot'
import { stateNumber, statePoints } from '../simulationAdapters'
import type { RendererProps } from './types'

/** Hull outline in world metres (Gymnasium's HULL_POLY / SCALE). */
const HULL = '-1,0.3 0.2,0.3 1.133,0.033 1.133,-0.267 -1,-0.267'
const LEG_W = 8 / 30
const LEG_H = 34 / 30

/** Distance, in metres, shown to the left and right of the walker. */
const VIEW_BEHIND = 4
const VIEW_AHEAD = 9
const VIEW_HEIGHT = 7

/** Side view of the walker and the terrain around it, driven only by backend frame state. */
export function BipedalWalker2D({ scene, store, palette }: RendererProps) {
  const frame = useFrameSnapshot(store)
  const s = (scene ?? {}) as Record<string, unknown>
  const finish = typeof s.finish_x === 'number' ? s.finish_x : null
  const x = stateNumber(frame, 'x', 4)
  const y = stateNumber(frame, 'y', 5.7)
  const angle = (stateNumber(frame, 'angle') * 180) / Math.PI
  const terrain = statePoints(frame, 'terrain')
  const legsRaw = frame?.state.legs
  const legs = Array.isArray(legsRaw) ? (legsRaw as number[][]) : []
  const fell = frame?.done === true && frame.outcome?.success === false
  const finished = frame?.done === true && frame.outcome?.success === true
  const ink = fell ? palette.bad : palette.agent
  const floor =
    terrain.length > 1
      ? terrain
      : ([
          [x - 20, 3.3],
          [x + 20, 3.3],
        ] as Array<[number, number]>)
  const lowest = Math.min(...floor.map(([, ty]) => ty), y) - 3
  const outline = floor.map(([tx, ty]) => `${tx},${ty}`).join(' ')
  const top = y + VIEW_HEIGHT / 2

  return (
    <svg
      role="img"
      aria-label="BipedalWalker side view"
      viewBox={`${x - VIEW_BEHIND} ${-top} ${VIEW_BEHIND + VIEW_AHEAD} ${VIEW_HEIGHT}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: '100%', height: '100%', background: palette.background }}
    >
      <g transform="scale(1 -1)">
        <polygon
          points={`${floor[0]?.[0]},${lowest} ${outline} ${floor[floor.length - 1]?.[0]},${lowest}`}
          fill={palette.floor}
          stroke={palette.structure}
          strokeWidth={0.05}
        />
        {finish !== null && finish > x - VIEW_BEHIND && finish < x + VIEW_AHEAD + 2 && (
          <line
            x1={finish}
            x2={finish}
            y1={lowest}
            y2={y + 4}
            stroke={finished ? palette.good : palette.agent}
            strokeWidth={0.06}
            strokeDasharray="0.3 0.2"
          />
        )}
        {legs.map(([lx = 0, ly = 0, la = 0], index) => (
          <rect
            key={index}
            data-testid="walker-leg"
            x={-(index % 2 === 0 ? LEG_W : LEG_W * 0.8) / 2}
            y={-LEG_H / 2}
            width={index % 2 === 0 ? LEG_W : LEG_W * 0.8}
            height={LEG_H}
            rx={0.04}
            fill={palette.background}
            stroke={ink}
            strokeWidth={0.05}
            transform={`translate(${lx} ${ly}) rotate(${(la * 180) / Math.PI})`}
          />
        ))}
        <polygon
          points={HULL}
          fill={palette.background}
          stroke={ink}
          strokeWidth={0.07}
          strokeLinejoin="round"
          transform={`translate(${x} ${y}) rotate(${angle})`}
        />
      </g>
    </svg>
  )
}
