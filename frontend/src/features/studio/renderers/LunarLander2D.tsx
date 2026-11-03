import { useFrameSnapshot } from '../useFrameSnapshot'
import { stateNumber, statePoints } from '../simulationAdapters'
import { lunarEngines } from './lunarEngines'
import type { RendererProps } from './types'

/** Lander body outline in world metres (Gymnasium's LANDER_POLY / SCALE). */
const BODY = '-0.467,0.567 -0.567,0 -0.567,-0.333 0.567,-0.333 0.567,0 0.467,0.567'

interface World {
  w: number
  h: number
}

function worldOf(scene: Record<string, unknown> | null): World {
  const s = (scene ?? {}) as Record<string, unknown>
  return {
    w: typeof s.world_w === 'number' ? s.world_w : 20,
    h: typeof s.world_h === 'number' ? s.world_h : 13.33,
  }
}

/** Side view of the lander, terrain and pad, driven only by backend frame state. */
export function LunarLander2D({ scene, store, palette }: RendererProps) {
  const frame = useFrameSnapshot(store)
  const world = worldOf(scene)
  const x = stateNumber(frame, 'x', world.w / 2)
  const y = stateNumber(frame, 'y', world.h * 0.95)
  const angle = (stateNumber(frame, 'angle') * 180) / Math.PI
  const terrain = statePoints(frame, 'terrain')
  const helipad = frame?.state.helipad
  const pad = Array.isArray(helipad) ? (helipad as number[]) : null
  const left = frame?.state.left_contact === true
  const right = frame?.state.right_contact === true
  const engines = lunarEngines(frame)
  const crashed = frame?.done === true && frame.outcome?.success === false
  const landed = frame?.done === true && frame.outcome?.success === true
  const ground =
    terrain.length > 1
      ? terrain
      : ([
          [0, 2],
          [world.w, 2],
        ] as Array<[number, number]>)
  const outline = ground.map(([tx, ty]) => `${tx},${ty}`).join(' ')
  const body = crashed ? palette.bad : palette.agent

  return (
    <svg
      role="img"
      aria-label="LunarLander side view"
      viewBox={`0 0 ${world.w} ${world.h}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: '100%', height: '100%', background: palette.background }}
    >
      <g transform={`translate(0 ${world.h}) scale(1 -1)`}>
        <polygon
          points={`0,0 ${outline} ${world.w},0`}
          fill={palette.floor}
          stroke={palette.structure}
          strokeWidth={0.05}
        />
        {pad && (
          <g stroke={landed ? palette.good : palette.agent} strokeWidth={0.07}>
            <line x1={pad[0]} x2={pad[1]} y1={pad[2]} y2={pad[2]} />
            {[pad[0], pad[1]].map((fx) => (
              <line
                key={fx}
                x1={fx}
                x2={fx}
                y1={pad[2]}
                y2={(pad[2] ?? 0) + 0.7}
                strokeWidth={0.04}
              />
            ))}
          </g>
        )}
        <g transform={`translate(${x} ${y}) rotate(${angle})`}>
          {engines.main > 0 && (
            <polygon
              data-testid="engine-main"
              points={`-0.2,-0.35 0.2,-0.35 0,${-0.35 - 0.6 * engines.main}`}
              fill={palette.accent}
            />
          )}
          {engines.side !== 0 && (
            <polygon
              data-testid="engine-side"
              points={`${-engines.side * 0.57},0.1 ${-engines.side * 0.57},0.3 ${-engines.side * 0.95},0.2`}
              fill={palette.accent}
            />
          )}
          {[-1, 1].map((side) => (
            <line
              key={side}
              x1={side * 0.5}
              y1={-0.3}
              x2={side * 0.85}
              y2={-0.85}
              stroke={(side < 0 ? left : right) ? palette.good : body}
              strokeWidth={0.07}
              strokeLinecap="round"
            />
          ))}
          <polygon
            points={BODY}
            fill={palette.background}
            stroke={body}
            strokeWidth={0.07}
            strokeLinejoin="round"
          />
        </g>
      </g>
    </svg>
  )
}
