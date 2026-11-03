import { useFrameSnapshot } from '../useFrameSnapshot'
import { adaptGridAgent, gridScene } from '../simulationAdapters'
import type { RendererProps } from './types'

/** Top-down view of the navigation grid, driven only by backend frame state. */
export function GridMaze2D({ scene, store, palette }: RendererProps) {
  const frame = useFrameSnapshot(store)
  const grid = gridScene(scene)
  if (!grid) return null
  const [row, col] = adaptGridAgent(frame, grid)
  const hit = frame?.collision === true

  return (
    <svg
      role="img"
      aria-label="Warehouse grid, top-down view"
      viewBox={`-0.5 -0.5 ${grid.cols + 1} ${grid.rows + 1}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: '100%', height: '100%', background: palette.background }}
    >
      <rect x={0} y={0} width={grid.cols} height={grid.rows} fill={palette.floor} stroke={palette.grid} strokeWidth={0.04} />
      {Array.from({ length: grid.rows + 1 }, (_, i) => (
        <line key={`r${i}`} x1={0} x2={grid.cols} y1={i} y2={i} stroke={palette.grid} strokeWidth={0.02} />
      ))}
      {Array.from({ length: grid.cols + 1 }, (_, i) => (
        <line key={`c${i}`} y1={0} y2={grid.rows} x1={i} x2={i} stroke={palette.grid} strokeWidth={0.02} />
      ))}
      {grid.obstacles.map(([r, c]) => (
        <rect key={`o${r}-${c}`} x={c + 0.06} y={r + 0.06} width={0.88} height={0.88} fill={palette.structure} />
      ))}
      <rect x={grid.goal[1] + 0.12} y={grid.goal[0] + 0.12} width={0.76} height={0.76} fill="none" stroke={palette.good} strokeWidth={0.08} />
      <circle cx={col + 0.5} cy={row + 0.5} r={0.3} fill={hit ? palette.bad : palette.agent} />
    </svg>
  )
}
