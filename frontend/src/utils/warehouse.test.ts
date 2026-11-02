import { describe, expect, it } from 'vitest'
import type {
  SimulationReplay,
  TrajectoryPoint,
  WarehouseCell,
  WarehouseEnvironmentSnapshot,
} from '../schemas/simulation'
import {
  cellIsObstacle,
  cellsEqual,
  cellInsideGrid,
  findLayoutIssues,
  findTrajectoryIssues,
  manhattanDistance,
  trajectoryIndexForTimestep,
} from './warehouse'

export function cell(row: number, col: number): WarehouseCell {
  return { row, col }
}

export function snapshot(
  overrides: Partial<WarehouseEnvironmentSnapshot> = {},
): WarehouseEnvironmentSnapshot {
  return {
    environment_id: 'env_demo',
    environment_version: 'warehouse_v1',
    rows: 8,
    cols: 10,
    start: cell(0, 0),
    goal: cell(7, 9),
    obstacles: [cell(2, 1), cell(2, 2), cell(5, 5)],
    run_id: null,
    episode_id: null,
    snapshot_at: null,
    schema_version: '1.0',
    ...overrides,
  }
}

export function point(timestep: number, at: WarehouseCell, terminated = false): TrajectoryPoint {
  return { timestep, cell: at, terminated }
}

export function replay(partial: Partial<SimulationReplay> = {}): SimulationReplay {
  return {
    environment: snapshot(),
    trajectory: [point(0, cell(0, 0)), point(1, cell(0, 1)), point(2, cell(0, 2))],
    faultMarkers: [],
    run_id: null,
    schema_version: '1.0',
    ...partial,
  }
}

describe('cell helpers', () => {
  it('compares cells structurally', () => {
    expect(cellsEqual(cell(1, 2), cell(1, 2))).toBe(true)
    expect(cellsEqual(cell(1, 2), cell(2, 1))).toBe(false)
  })

  it('bounds checks cannot be softened by fractional coordinates', () => {
    expect(cellInsideGrid(cell(0, 0), 8, 10)).toBe(true)
    expect(cellInsideGrid(cell(7, 9), 8, 10)).toBe(true)
    expect(cellInsideGrid(cell(8, 0), 8, 10)).toBe(false)
    expect(cellInsideGrid(cell(-1, 0), 8, 10)).toBe(false)
    expect(cellInsideGrid(cell(1.5, 1), 8, 10)).toBe(false)
  })

  it('computes 4-connectivity distance and obstacle membership', () => {
    expect(manhattanDistance(cell(0, 0), cell(3, 4))).toBe(7)
    expect(manhattanDistance(cell(2, 2), cell(2, 4))).toBe(2)
    expect(cellIsObstacle(cell(2, 1), [cell(2, 1), cell(2, 2)])).toBe(true)
    expect(cellIsObstacle(cell(0, 0), [cell(2, 1)])).toBe(false)
  })
})

describe('findLayoutIssues', () => {
  it('accepts a valid concrete warehouse layout', () => {
    expect(findLayoutIssues(snapshot())).toEqual([])
  })

  it('reports each degenerate grid honestly', () => {
    const issues = findLayoutIssues(snapshot({ rows: 6, cols: 10 })) // start (0,0) ok, goal (7,9) outside
    expect(issues.some((issue) => /goal cell is outside/.test(issue))).toBe(true)

    expect(findLayoutIssues(snapshot({ start: cell(3, 3), goal: cell(3, 3) }))).toContain(
      'The recorded start and goal cells coincide.',
    )
    expect(
      findLayoutIssues(snapshot({ obstacles: [cell(0, 0)] })).some((issue) =>
        /overlaps the recorded start/.test(issue),
      ),
    ).toBe(true)
    expect(
      findLayoutIssues(snapshot({ obstacles: [cell(7, 9), cell(99, 0)] })).some((issue) =>
        /goal cell/.test(issue),
      ),
    ).toBe(true)
  })

  it('reports invalid dimensions instead of rendering a plausible grid', () => {
    expect(findLayoutIssues(snapshot({ rows: 0, cols: 10 }))).toContain(
      'Grid dimensions are missing or invalid.',
    )
    expect(findLayoutIssues(snapshot({ rows: Number.NaN, cols: 4 }))).toContain(
      'Grid dimensions are missing or invalid.',
    )
  })
})

describe('findTrajectoryIssues', () => {
  it('accepts a walking 4-connected path', () => {
    expect(findTrajectoryIssues(replay())).toEqual([])
  })

  it('flags positions outside the grid — never clips them silently', () => {
    const issues = findTrajectoryIssues(
      replay({ trajectory: [point(0, cell(0, 0)), point(1, cell(9, 0))] }),
    )
    expect(issues.some((issue) => /outside the recorded grid/.test(issue))).toBe(true)
  })

  it('flags descending timesteps', () => {
    const issues = findTrajectoryIssues(
      replay({ trajectory: [point(5, cell(0, 0)), point(4, cell(0, 1))] }),
    )
    expect(issues).toContain('The recorded trajectory is not in ascending timestep order.')
  })

  it('flags impossible jumps: distance beyond elapsed timesteps', () => {
    const issues = findTrajectoryIssues(
      replay({ trajectory: [point(0, cell(0, 0)), point(1, cell(7, 9))] }),
    )
    expect(issues.some((issue) => /farther than elapsed timesteps allow/.test(issue))).toBe(true)
  })

  it('permits the environment reset across a terminated episode boundary', () => {
    const issues = findTrajectoryIssues(
      replay({
        // Episode 1 ends at (7,9); the environment resets and episode 2 starts
        // at (0,0) — a discontinuity recorded behaviour requires.
        trajectory: [
          point(800, cell(0, 4)),
          point(812, cell(7, 9), true),
          point(813, cell(0, 0)),
          point(814, cell(0, 1)),
        ],
      }),
    )
    expect(issues).toEqual([])
  })

  it('allows a partial recording that starts mid-episode without flagging axes', () => {
    // A recording that starts at timestep 800 has no "previous" position to
    // compare against, so no adjacency charge is raised at the start.
    expect(
      findTrajectoryIssues(
        replay({ trajectory: [point(800, cell(0, 4)), point(801, cell(0, 5))] }),
      ),
    ).toEqual([])
  })
})

describe('trajectoryIndexForTimestep', () => {
  const trajectory = [point(800, cell(0, 0)), point(812, cell(0, 1)), point(848, cell(0, 2))]

  it('reports -1 before the recording starts', () => {
    expect(trajectoryIndexForTimestep(trajectory, 799)).toBe(-1)
  })

  it('selects the latest recorded point at or below the request', () => {
    expect(trajectoryIndexForTimestep(trajectory, 800)).toBe(0)
    expect(trajectoryIndexForTimestep(trajectory, 813)).toBe(1)
    expect(trajectoryIndexForTimestep(trajectory, 900)).toBe(2)
  })
})
