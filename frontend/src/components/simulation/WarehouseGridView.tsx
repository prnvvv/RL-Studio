import type { ReactNode } from 'react'
import type { SimulationReplay, WarehouseCell } from '../../schemas/simulation'
import { cellInsideGrid, cellIsObstacle, trajectoryIndexForTimestep } from '../../utils/warehouse'
import { DEFAULT_DISPLAY_OPTIONS, type WarehouseDisplayOptions } from './displayOptions'

/**
 * Data-bound warehouse grid renderer.
 *
 * Draws EXACTLY what a recorded replay contains: the recorded layout, the
 * trajectory up to the requested playback timestep, the agent position at
 * that timestep, and fault markers only where fault events were recorded.
 * It never interpolates positions, never authors environment state, and
 * never draws anything beyond the recorded window.
 *
 * Points outside the recorded grid cannot be drawn; whoever composes this
 * view must report them (see `findTrajectoryIssues`) — silent clipping is
 * the one thing this renderer must never do.
 *
 * Purely a display surface: monochrome tokens only, correct in both themes.
 */

interface WarehouseGridViewProps {
  replay: SimulationReplay
  /** Playback cursor in the recording's own timestep units. */
  timestep: number
  options?: WarehouseDisplayOptions
}

const CELL = 26
const PADDING = 6

function cellOrigin(cell: WarehouseCell): { x: number; y: number } {
  return { x: PADDING + cell.col * CELL, y: PADDING + cell.row * CELL }
}

function centeredAt(cx: number, cy: number, testId: string, children: ReactNode): ReactNode {
  return (
    <g data-testid={testId} transform={`translate(${cx + CELL / 2}, ${cy + CELL / 2})`}>
      {children}
    </g>
  )
}

export function WarehouseGridView({
  replay,
  timestep,
  options = DEFAULT_DISPLAY_OPTIONS,
}: WarehouseGridViewProps) {
  const { environment, trajectory, faultMarkers } = replay
  const { rows, cols, start, goal, obstacles } = environment

  const cursorIndex = trajectoryIndexForTimestep(trajectory, timestep)
  const cursorPoint = cursorIndex >= 0 ? trajectory[cursorIndex] : null

  const width = cols * CELL + PADDING * 2
  const height = rows * CELL + PADDING * 2

  // Recorded positions up to the cursor, drawn only when inside the grid.
  const walked = options.showTrajectory
    ? trajectory.slice(0, cursorIndex + 1).filter((point) => cellInsideGrid(point.cell, rows, cols))
    : []

  // Fault markers draw only when the recording holds a position at the
  // marker's EXACT recorded timestep — the grid never invents a placement.
  const drawnMarkers = faultMarkers.flatMap((marker) => {
    const point = trajectory.find((candidate) => candidate.timestep === marker.at_timestep)
    if (!point || !cellInsideGrid(point.cell, rows, cols)) return []
    return [{ marker, cell: point.cell }]
  })

  const agentLabel = cursorPoint
    ? `Agent at row ${cursorPoint.cell.row}, column ${cursorPoint.cell.col} at timestep ${cursorPoint.timestep}`
    : 'Before the recording starts: no agent position recorded yet'

  const description = [
    `Recorded warehouse grid, ${rows} rows by ${cols} columns.`,
    agentLabel,
    options.showTrajectory ? `${walked.length} recorded positions shown up to the cursor.` : null,
    drawnMarkers.length > 0 ? `${drawnMarkers.length} recorded fault marker(s) shown.` : null,
    'Recorded replay; not a live simulation.',
  ]
    .filter((line): line is string => line !== null)
    .join(' ')

  const goalOrigin = cellOrigin(goal)
  const agentOrigin = cursorPoint ? cellOrigin(cursorPoint.cell) : null
  const startOrigin = cellOrigin(start)

  return (
    <svg
      role="img"
      aria-label={description}
      data-testid="warehouse-grid"
      viewBox={`0 0 ${width} ${height}`}
      style={{ width: '100%', maxWidth: width * 2, height: 'auto', display: 'block' }}
      fontFamily="var(--font-sans)"
    >
      {/* Floor frame and grid lines */}
      <rect
        x={0}
        y={0}
        width={width}
        height={height}
        fill="none"
        stroke="var(--border-primary)"
        strokeWidth={1}
      />
      {Array.from({ length: rows - 1 }, (_, index) => (
        <line
          key={`h${index}`}
          x1={PADDING}
          y1={PADDING + (index + 1) * CELL}
          x2={width - PADDING}
          y2={PADDING + (index + 1) * CELL}
          stroke="var(--border-secondary)"
          strokeWidth={1}
        />
      ))}
      {Array.from({ length: cols - 1 }, (_, index) => (
        <line
          key={`v${index}`}
          x1={PADDING + (index + 1) * CELL}
          y1={PADDING}
          x2={PADDING + (index + 1) * CELL}
          y2={height - PADDING}
          stroke="var(--border-secondary)"
          strokeWidth={1}
        />
      ))}

      {/* Obstacles: filled shelf cells, display-only toggle */}
      {options.showObstacles &&
        obstacles.map((obstacle) => {
          if (!cellInsideGrid(obstacle, rows, cols) || cellIsObstacle(obstacle, [start, goal]))
            return null
          const origin = cellOrigin(obstacle)
          return (
            <rect
              key={`obs-${obstacle.row}-${obstacle.col}`}
              data-testid="obstacle-cell"
              data-row={obstacle.row}
              data-col={obstacle.col}
              x={origin.x + 1.5}
              y={origin.y + 1.5}
              width={CELL - 3}
              height={CELL - 3}
              fill="var(--text-muted)"
              opacity={0.85}
            >
              <title>{`Obstacle (row ${obstacle.row}, column ${obstacle.col})`}</title>
            </rect>
          )
        })}

      {/* Recorded trajectory dots up to the cursor */}
      {walked.map((point, index) => {
        const origin = cellOrigin(point.cell)
        return (
          <circle
            key={`traj-${index}`}
            data-testid="trajectory-dot"
            cx={origin.x + CELL / 2}
            cy={origin.y + CELL / 2}
            r={2.4}
            fill="var(--text-primary)"
          />
        )
      })}

      {/* Start cell: dashed outline square from the recorded layout */}
      <rect
        data-testid="start-cell"
        data-row={start.row}
        data-col={start.col}
        x={startOrigin.x + 4}
        y={startOrigin.y + 4}
        width={CELL - 8}
        height={CELL - 8}
        fill="none"
        stroke="var(--text-secondary)"
        strokeWidth={1.2}
        strokeDasharray="3 2"
      >
        <title>{`Start cell (row ${start.row}, column ${start.col})`}</title>
      </rect>

      {/* Goal cell: target marker, display-only toggle */}
      {options.showGoal &&
        centeredAt(
          goalOrigin.x,
          goalOrigin.y,
          'goal-marker',
          <>
            <circle r={CELL / 3.4} fill="none" stroke="var(--text-primary)" strokeWidth={1.4} />
            <path
              d={`M ${-CELL / 7} 0 H ${CELL / 7} M 0 ${-CELL / 7} V ${CELL / 7}`}
              stroke="var(--text-primary)"
              strokeWidth={1.2}
            />
            <title>{`Goal cell (row ${goal.row}, column ${goal.col})`}</title>
          </>,
        )}

      {/* Fault markers, only at recorded event positions */}
      {drawnMarkers.map(({ marker, cell }) => {
        const origin = cellOrigin(cell)
        return (
          <g
            key={marker.event_id}
            data-testid="fault-marker"
            data-event-id={marker.event_id}
            transform={`translate(${origin.x + CELL / 2}, ${origin.y + CELL / 2})`}
          >
            <circle r={CELL / 3.2} fill="none" stroke="var(--text-primary)" strokeWidth={1.4} />
            <path
              d={`M ${-CELL / 6} ${-CELL / 6} L ${CELL / 6} ${CELL / 6} M ${CELL / 6} ${-CELL / 6} L ${-CELL / 6} ${CELL / 6}`}
              stroke="var(--text-primary)"
              strokeWidth={1.4}
              fill="none"
            />
            <title>{`Recorded fault event ${marker.event_id} at timestep ${marker.at_timestep}: ${marker.label ?? marker.fault_type}`}</title>
          </g>
        )
      })}

      {/* Agent marker at the playback cursor, display-only toggle */}
      {options.showAgent &&
      cursorPoint &&
      agentOrigin &&
      cellInsideGrid(cursorPoint.cell, rows, cols)
        ? centeredAt(
            agentOrigin.x,
            agentOrigin.y,
            'agent-marker',
            <>
              <circle r={CELL / 3} fill="var(--text-primary)" />
              <path d="M -3 0 L 0 -3 L 3 0 L 0 3 Z" fill="var(--bg-primary)" stroke="none" />
              <title>{agentLabel}</title>
            </>,
          )
        : null}
    </svg>
  )
}
