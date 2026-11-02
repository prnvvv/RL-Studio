/**
 * Warehouse-grid geometry and state-accuracy helpers.
 *
 * Pure functions used by the simulation viewers and their tests. They encode
 * the environment's invariant set (`backend/environments/config.py`): bounded
 * grid, 4-connectivity, obstacles never covering start or goal. View code
 * validates recorded state through these helpers instead of re-deriving
 * rules ad hoc, so visual rendering and validation stay consistent.
 */
import type {
  SimulationReplay,
  TrajectoryPoint,
  WarehouseCell,
  WarehouseEnvironmentSnapshot,
} from '../schemas/simulation'

/** Two cells refer to the same grid position. */
export function cellsEqual(a: WarehouseCell, b: WarehouseCell): boolean {
  return a.row === b.row && a.col === b.col
}

/** The cell lies within a `rows x cols` grid. */
export function cellInsideGrid(cell: WarehouseCell, rows: number, cols: number): boolean {
  return (
    Number.isInteger(cell.row) &&
    Number.isInteger(cell.col) &&
    cell.row >= 0 &&
    cell.col >= 0 &&
    cell.row < rows &&
    cell.col < cols
  )
}

/** Manhattan 4-neighbour distance (0 = same cell). */
export function manhattanDistance(a: WarehouseCell, b: WarehouseCell): number {
  return Math.abs(a.row - b.row) + Math.abs(a.col - b.col)
}

/** Obstacle-set membership with tolerance for unordered duplicates. */
export function cellIsObstacle(cell: WarehouseCell, obstacles: WarehouseCell[]): boolean {
  return obstacles.some((obstacle) => cellsEqual(obstacle, cell))
}

/**
 * Validate a recorded environment layout. Returns human-readable issue lines
 * so a viewer can honestly flag unusable records instead of silently drawing
 * a plausible-looking but wrong warehouse.
 */
export function findLayoutIssues(snapshot: WarehouseEnvironmentSnapshot): string[] {
  const issues: string[] = []
  const { rows, cols, start, goal, obstacles } = snapshot

  if (!Number.isInteger(rows) || !Number.isInteger(cols) || rows < 1 || cols < 1) {
    issues.push('Grid dimensions are missing or invalid.')
    return issues
  }
  if (!cellInsideGrid(start, rows, cols)) {
    issues.push('The recorded start cell is outside the recorded grid.')
  }
  if (!cellInsideGrid(goal, rows, cols)) {
    issues.push('The recorded goal cell is outside the recorded grid.')
  }
  if (cellsEqual(start, goal)) {
    issues.push('The recorded start and goal cells coincide.')
  }
  for (const obstacle of obstacles) {
    if (!cellInsideGrid(obstacle, rows, cols)) {
      issues.push(
        `An obstacle cell (${obstacle.row}, ${obstacle.col}) lies outside the recorded grid.`,
      )
    } else if (cellsEqual(obstacle, start) || cellsEqual(obstacle, goal)) {
      issues.push(
        `An obstacle overlaps the recorded ${cellsEqual(obstacle, start) ? 'start' : 'goal'} cell.`,
      )
    }
  }
  return issues
}

/**
 * Validate a recorded trajectory against its environment layout. Rendering
 * never silently clips unrenderable points: the viewer reports them.
 *
 * Consecutive steps must be reachable within the elapsed timesteps, except
 * across an episode boundary: when a point is marked `terminated`, the
 * environment resets and the next recorded position legitimately restarts at
 * the start cell.
 */
export function findTrajectoryIssues(replay: SimulationReplay): string[] {
  const issues: string[] = []
  const { environment, trajectory } = replay
  const { rows, cols } = environment

  for (const index in trajectory) {
    const point = trajectory[index] as TrajectoryPoint
    if (!cellInsideGrid(point.cell, rows, cols)) {
      issues.push(`Timestep ${point.timestep} records a position outside the recorded grid.`)
    }
  }

  for (let index = 1; index < trajectory.length; index += 1) {
    const previous = trajectory[index - 1] as TrajectoryPoint
    const point = trajectory[index] as TrajectoryPoint
    if (point.timestep <= previous.timestep) {
      issues.push('The recorded trajectory is not in ascending timestep order.')
      break
    }
    if (previous.terminated) {
      // Episode completed and the environment reset: arrival at the start
      // cell of the next episode is recorded behaviour, not corrupted data.
      continue
    }
    const distance = manhattanDistance(previous.cell, point.cell)
    if (distance > point.timestep - previous.timestep) {
      issues.push(
        `Steps ${previous.timestep} -> ${point.timestep} move farther than elapsed timesteps allow; part of the recording is missing.`,
      )
      break
    }
  }
  return issues
}

/**
 * Index of the trajectory point that covers a requested timestep: the
 * latest recorded point whose timestep is `<= requested`. Returns `-1`
 * before the recording starts (nothing has happened yet).
 */
export function trajectoryIndexForTimestep(
  trajectory: TrajectoryPoint[],
  timestep: number,
): number {
  let low = 0
  let high = trajectory.length - 1
  let best = -1
  while (low <= high) {
    const mid = (low + high) >>> 1
    const candidate = trajectory[mid]?.timestep ?? 0
    if (candidate <= timestep) {
      best = mid
      low = mid + 1
    } else {
      high = mid - 1
    }
  }
  return best
}
