/**
 * Development mock adapter for warehouse simulation replays.
 *
 * Implements the planned simulation contract (see `schemas/simulation.ts`)
 * with a deterministic fixture aligned with the canonical warehouse
 * reward-scaling demo scenario: the recorded episode reaches the goal cell at
 * timestep 812 — the same recorded event (`evt_demo_step_812`) the demo
 * incident cites as evidence for the observed goal reward of 40.
 *
 * The fixture covers timesteps 796-825: all of episode 1 (terminated at the
 * goal at 812) plus the start of episode 2 after the environment reset, so
 * playback can demonstrate a full arrive-and-restart cycle.
 *
 * Requires the explicit `VITE_USE_MOCKS=true` opt-in (fail-closed). The
 * fixtures are sample data — never presented as live backend behaviour.
 */
import type { SimulationReplay, TrajectoryPoint } from '../schemas/simulation'
import { assertMocksEnabled } from './index'
import { DEMO_RUN_ID } from './verification'

const START = { row: 0, col: 0 }
const GOAL = { row: 7, col: 9 }

/**
 * Shelf layout matching a plausible `warehouse_v1` record: two shelf rows the
 * agent must route around. Never overlaps start or goal.
 */
const OBSTACLES = [
  { row: 2, col: 1 },
  { row: 2, col: 2 },
  { row: 2, col: 3 },
  { row: 2, col: 4 },
  { row: 5, col: 5 },
  { row: 5, col: 6 },
  { row: 5, col: 7 },
]

function walk(
  from: TrajectoryPoint['cell'],
  to: { row: number; col: number },
  timesteps: number[],
): TrajectoryPoint[] {
  const points: TrajectoryPoint[] = []
  let [row, col] = [from.row, from.col]
  let index = 0
  while (row !== to.row || col !== to.col) {
    const timestep = timesteps[index] ?? Number.NaN
    if (Number.isNaN(timestep)) break
    if (row !== to.row) {
      row += to.row > row ? 1 : -1
    } else {
      col += to.col > col ? 1 : -1
    }
    points.push({ timestep, cell: { row, col }, terminated: false })
    index += 1
  }
  return points
}

function buildDemoReplay(): SimulationReplay {
  const trajectory: TrajectoryPoint[] = [{ timestep: 796, cell: START, terminated: false }]
  // Episode 1: east along row 0, then south to the goal — 17 recorded steps.
  trajectory.push(...walk(START, { row: 0, col: 9 }, [797, 798, 799, 800, 801, 802, 803, 804, 805]))
  trajectory.push(...walk({ row: 0, col: 9 }, GOAL, [806, 807, 808, 809, 810, 811, 812]))
  // Arriving at the goal terminates the episode (recorded at evt_demo_step_812).
  trajectory[trajectory.length - 1]!.terminated = true
  // Episode 2 begins at the reset cell and walks east again; the recording
  // ends mid-episode (heading south at (4,8)) — an honest partial window.
  trajectory.push({ timestep: 813, cell: START, terminated: false })
  trajectory.push(...walk(START, { row: 0, col: 8 }, [814, 815, 816, 817, 818, 819, 820, 821]))
  trajectory.push(...walk({ row: 0, col: 8 }, { row: 4, col: 8 }, [822, 823, 824, 825]))

  return {
    environment: {
      environment_id: 'warehouse_2d',
      environment_version: 'warehouse_v1',
      rows: 8,
      cols: 10,
      start: START,
      goal: GOAL,
      obstacles: OBSTACLES,
      run_id: DEMO_RUN_ID,
      episode_id: null,
      snapshot_at: '2026-10-25T12:10:00Z',
      schema_version: '1.0',
    },
    trajectory,
    // A marker exists ONLY where a fault-injection event was recorded. The
    // 812 event is the same evidence the demo incident cites.
    faultMarkers: [
      {
        event_id: 'evt_demo_step_812',
        at_timestep: 812,
        fault_type: 'reward_scale_mismatch',
        label: 'Goal reached during the fault-injected interval',
      },
    ],
    run_id: DEMO_RUN_ID,
    schema_version: '1.0',
  }
}

/** Built once; the fixture is deterministic and stateless to read. */
let demoReplay: SimulationReplay | null = null

export interface MockSimulationAdapter {
  getRunSimulation(runId: string): Promise<SimulationReplay | null>
}

/**
 * Mock-mode adapter keyed by the demo run id. Any other id resolves to
 * `null`, which the service layer turns into an honest `not_found` — the
 * fixtures never pretend arbitrary runs have recordings.
 */
export const mockSimulationAdapter: MockSimulationAdapter = {
  async getRunSimulation(runId) {
    assertMocksEnabled('simulation.getRunSimulation')
    if (runId !== DEMO_RUN_ID) return null
    demoReplay = demoReplay ?? buildDemoReplay()
    return demoReplay
  },
}
