import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WarehouseGridView } from './WarehouseGridView'
import { DEFAULT_DISPLAY_OPTIONS } from './displayOptions'
import type { SimulationReplay, TrajectoryPoint, WarehouseCell } from '../../schemas/simulation'

// Local fixture builders — deliberately not shared with the guard-test module
// (importing a test module would re-register its suites in this file's run).
function cell(row: number, col: number): WarehouseCell {
  return { row, col }
}

function point(timestep: number, at: WarehouseCell, terminated = false): TrajectoryPoint {
  return { timestep, cell: at, terminated }
}

const LAYOUT = {
  environment: {
    environment_id: 'env_demo_grid',
    environment_version: 'warehouse_v1',
    rows: 8,
    cols: 10,
    start: cell(0, 0),
    goal: cell(7, 9),
    obstacles: [cell(2, 1), cell(2, 2), cell(5, 5)],
    run_id: 'run_demo_warehouse_ppo',
    episode_id: null,
    snapshot_at: null,
    schema_version: '1.0',
  },
  schema_version: '1.0',
  run_id: 'run_demo_warehouse_ppo',
}

function demoReplay(overrides: Partial<SimulationReplay> = {}): SimulationReplay {
  return {
    ...LAYOUT,
    trajectory: [point(0, cell(0, 0)), point(1, cell(0, 1)), point(2, cell(0, 2))],
    faultMarkers: [],
    ...overrides,
  }
}

describe('WarehouseGridView', () => {
  it('announces itself as a recorded replay, not a live simulation', () => {
    render(<WarehouseGridView replay={demoReplay()} timestep={2} />)
    const label = screen.getByTestId('warehouse-grid').getAttribute('aria-label') ?? ''
    expect(label).toMatch(/recorded replay; not a live simulation/i)
    expect(label).toMatch(/8 rows by 10 columns/)
  })

  it('renders the recorded layout: start, goal, and obstacles', () => {
    render(<WarehouseGridView replay={demoReplay()} timestep={2} />)
    expect(screen.getByTestId('start-cell')).toHaveAttribute('data-row', '0')
    expect(screen.getByTestId('goal-marker')).toBeInTheDocument()
    expect(screen.getAllByTestId('obstacle-cell')).toHaveLength(3)
  })

  it('truncates the trajectory strictly at the playback cursor', () => {
    const { unmount } = render(<WarehouseGridView replay={demoReplay()} timestep={1} />)
    // Two recorded points (timesteps 0..1) are walked, not the later one.
    expect(screen.getAllByTestId('trajectory-dot')).toHaveLength(2)
    unmount()

    render(<WarehouseGridView replay={demoReplay()} timestep={2} />)
    expect(screen.getAllByTestId('trajectory-dot')).toHaveLength(3)
  })

  it('moves the agent to the recorded position at the cursor and reports it', () => {
    render(<WarehouseGridView replay={demoReplay()} timestep={1} />)
    const agent = screen.getByTestId('agent-marker')
    expect(agent.textContent ?? '').toMatch(/row 0, column 1 at timestep 1/)
  })

  it('shows no agent marker before the recording starts', () => {
    render(<WarehouseGridView replay={demoReplay()} timestep={-1} />)
    expect(screen.queryByTestId('agent-marker')).not.toBeInTheDocument()
    expect(screen.queryAllByTestId('trajectory-dot')).toHaveLength(0)
    expect(screen.getByTestId('warehouse-grid')).toHaveAttribute(
      'aria-label',
      expect.stringMatching(/before the recording starts/i),
    )
  })

  it('never draws trajectory points outside the recorded grid', () => {
    const trajectory: TrajectoryPoint[] = [
      point(0, cell(0, 0)),
      point(1, cell(0, 1)),
      // Corrupt record: outside of the 8x10 grid; the composing viewer must
      // report this — the renderer only avoids silently drawing it.
      point(2, cell(99, 99)),
    ]
    render(<WarehouseGridView replay={demoReplay({ trajectory })} timestep={2} />)
    // Only the two in-grid points can be drawn...
    expect(screen.getAllByTestId('trajectory-dot')).toHaveLength(2)
    // ...and the accessible description cannot claim the third was drawn.
    const label = screen.getByTestId('warehouse-grid').getAttribute('aria-label') ?? ''
    expect(label).toMatch(/2 recorded positions/)
  })

  it('places fault markers only at their recorded event position', () => {
    // A marker whose timestep has no recorded position must NOT be drawn.
    const unplaceable = demoReplay({
      faultMarkers: [
        {
          event_id: 'evt_demo_step_812',
          at_timestep: 812,
          fault_type: 'reward_scale_mismatch',
          label: null,
        },
      ],
    })
    const { unmount } = render(<WarehouseGridView replay={unplaceable} timestep={2} />)
    expect(screen.queryByTestId('fault-marker')).not.toBeInTheDocument()
    unmount()

    // A marker at a recorded timestep draws on the recorded agent cell.
    const positioned = demoReplay({
      faultMarkers: [
        {
          event_id: 'evt_demo_step_812',
          at_timestep: 1,
          fault_type: 'reward_scale_mismatch',
          label: 'recorded interval',
        },
      ],
    })
    render(<WarehouseGridView replay={positioned} timestep={2} />)
    expect(screen.getByTestId('fault-marker')).toHaveAttribute('data-event-id', 'evt_demo_step_812')
  })

  it('honours display-only toggles without mutating the replay data', () => {
    const localReplay = demoReplay()
    const { unmount } = render(
      <WarehouseGridView
        replay={localReplay}
        timestep={2}
        options={{
          ...DEFAULT_DISPLAY_OPTIONS,
          showObstacles: false,
          showGoal: false,
          showTrajectory: false,
        }}
      />,
    )
    expect(screen.queryByTestId('obstacle-cell')).not.toBeInTheDocument()
    expect(screen.queryByTestId('goal-marker')).not.toBeInTheDocument()
    expect(screen.queryByTestId('trajectory-dot')).not.toBeInTheDocument()
    // The start cell is recorded layout, not an entity toggle.
    expect(screen.getByTestId('start-cell')).toBeInTheDocument()
    unmount()

    // Toggling displays never alters the underlying recording.
    expect(localReplay.trajectory).toHaveLength(3)
    expect(localReplay.environment.obstacles).toHaveLength(3)
  })
})
