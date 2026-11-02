import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { WarehousePlaybackViewer } from './WarehousePlaybackViewer'
import type { SimulationService } from '../../services/simulation'
import type {
  SimulationReplay,
  TrajectoryPoint,
  WarehouseCell,
  FaultMarker,
} from '../../schemas/simulation'
import { labeledMockData, type MockData } from '../../mocks'
import type { ServiceResult } from '../../services/types'

function cell(row: number, col: number): WarehouseCell {
  return { row, col }
}

function point(timestep: number, at: WarehouseCell, terminated = false): TrajectoryPoint {
  return { timestep, cell: at, terminated }
}

const LAYOUT = {
  environment: {
    environment_id: 'env_demo_viewer',
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
  run_id: 'run_demo_warehouse_ppo',
  schema_version: '1.0',
}

const DEMO_MARKERS: FaultMarker[] = [
  {
    event_id: 'evt_demo_step_797',
    at_timestep: 797,
    fault_type: 'reward_scale_mismatch',
    label: 'recorded interval',
  },
]

function fixture(overrides: Partial<SimulationReplay> = {}): SimulationReplay {
  return {
    ...LAYOUT,
    trajectory: [point(796, cell(0, 0)), point(797, cell(0, 1)), point(798, cell(0, 2))],
    faultMarkers: DEMO_MARKERS,
    ...overrides,
  }
}

type StubResult = ServiceResult<SimulationReplay | MockData<SimulationReplay>>

function stubService(fixedResult: StubResult | Promise<StubResult>): {
  service: SimulationService
  calls: number[]
} {
  const calls: number[] = []
  const service: SimulationService = {
    getRunSimulation() {
      calls.push(calls.length)
      return Promise.resolve(fixedResult)
    },
  }
  return { service, calls }
}

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('WarehousePlaybackViewer', () => {
  it('renders an honest loading state while the replay request is in flight', () => {
    const { service } = stubService(new Promise<ServiceResult<SimulationReplay>>(() => {}))
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    render(<WarehousePlaybackViewer runId="run_demo_warehouse_ppo" service={service} />)

    expect(screen.getByText(/Loading recorded simulation replay/)).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Loading data' })).toBeInTheDocument()
    expect(screen.queryByTestId('warehouse-grid')).not.toBeInTheDocument()
  })

  it('plays fixture-backed replays and keeps the shared sample-data label visible', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    const { service } = stubService({ state: 'ok', data: labeledMockData(fixture()) })
    render(<WarehousePlaybackViewer runId="run_demo_warehouse_ppo" service={service} />)

    await waitFor(() => expect(screen.getByTestId('warehouse-replay-surface')).toBeInTheDocument())
    // The shared "Sample data" badge travels with the fixture.
    expect(screen.getByText('Sample data')).toBeInTheDocument()
    // The recorded window is announced in the recording's own units.
    expect(screen.getByTestId('warehouse-replay-surface').textContent).toMatch(
      /Recorded timesteps 796–798/,
    )
    // Playback starts at the first recorded timestep.
    expect(screen.getByRole('slider')).toHaveAttribute('value', '796')
    expect(screen.getByTestId('fault-marker')).toBeInTheDocument()
  })

  it('renders the fallback with an honest empty state when no replay exists', async () => {
    const { service } = stubService({
      state: 'error',
      error: { kind: 'not_found', message: 'No simulation recording found for this run.' },
    })
    render(
      <WarehousePlaybackViewer
        runId="run_other"
        service={service}
        fallback={<div data-testid="illustration-fallback" />}
      />,
    )

    await waitFor(() =>
      expect(screen.getByText(/No recorded simulation replay for this run/)).toBeInTheDocument(),
    )
    expect(screen.getByTestId('illustration-fallback')).toBeInTheDocument()
    expect(screen.queryByTestId('warehouse-grid')).not.toBeInTheDocument()
  })

  it('offers a safe retry on transport errors and reloads on click', async () => {
    const { service, calls } = stubService({
      state: 'error',
      error: { kind: 'unavailable', message: 'Simulation service is temporarily unavailable.' },
    })
    render(<WarehousePlaybackViewer runId="run_demo_warehouse_ppo" service={service} />)

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    // Replay fetching is a read-only GET, so a retry control is safe.
    fireEvent.click(screen.getByRole('button', { name: 'Retry loading' }))
    expect(calls.length).toBe(2)
  })

  it('refuses to draw a layout that fails the recorded-grid guards', async () => {
    const { service } = stubService({
      state: 'ok',
      data: labeledMockData(fixture({ environment: { ...LAYOUT.environment, goal: cell(99, 9) } })),
    })
    render(<WarehousePlaybackViewer runId="run_demo_warehouse_ppo" service={service} />)

    await waitFor(() => expect(screen.getByRole('note')).toBeInTheDocument())
    expect(screen.getByRole('note').textContent).toMatch(/goal cell is outside the recorded grid/i)
    // An unrenderable record must never be drawn into something plausible.
    expect(screen.queryByTestId('warehouse-grid')).not.toBeInTheDocument()
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
  })

  it('reports trajectory accuracy issues beside the rendered grid', async () => {
    const { service } = stubService({
      state: 'ok',
      data: labeledMockData(
        fixture({
          trajectory: [point(796, cell(0, 0)), point(797, cell(9, 9))],
        }),
      ),
    })
    render(<WarehousePlaybackViewer runId="run_demo_warehouse_ppo" service={service} />)

    await waitFor(() => expect(screen.getByTestId('warehouse-grid')).toBeInTheDocument())
    const note = screen.getByRole('note')
    expect(note.textContent).toMatch(/outside the recorded grid/i)
    expect(note.textContent).toMatch(/farther than elapsed timesteps allow/)
  })

  it('honours display toggles as view-only preferences', async () => {
    const { service } = stubService({ state: 'ok', data: labeledMockData(fixture()) })
    render(<WarehousePlaybackViewer runId="run_demo_warehouse_ppo" service={service} />)

    await waitFor(() => expect(screen.getByTestId('warehouse-grid')).toBeInTheDocument())
    // Playback starts at the first recorded timestep: only that position is
    // walked so far, though all three fault-less layout cells render.
    expect(screen.getAllByTestId('trajectory-dot')).toHaveLength(1)

    // Step the cursor forward through the recorded timesteps.
    const stepButton = screen.getByRole('button', { name: 'Step forward one recorded timestep' })
    fireEvent.click(stepButton)
    fireEvent.click(stepButton)
    expect(screen.getAllByTestId('trajectory-dot')).toHaveLength(3)

    const trajectoryToggle = screen.getByRole('checkbox', { name: 'Trajectory' })
    expect(trajectoryToggle).toBeChecked()
    fireEvent.click(trajectoryToggle)
    expect(screen.queryByTestId('trajectory-dot')).not.toBeInTheDocument()

    // Toggles change nothing about the underlying record: the recorded window
    // text stays intact and other layers still render.
    expect(screen.getByTestId('warehouse-replay-surface').textContent).toMatch(
      /Recorded timesteps 796–798/,
    )
    expect(screen.getByTestId('fault-marker')).toBeInTheDocument()
  })

  it('keeps an empty recording honest: layout shown, nothing to play', async () => {
    const { service } = stubService({
      state: 'ok',
      data: labeledMockData(fixture({ trajectory: [] })),
    })
    render(<WarehousePlaybackViewer runId="run_demo_warehouse_ppo" service={service} />)

    await waitFor(() =>
      expect(screen.getByTestId('warehouse-replay-surface').textContent).toMatch(
        /no agent positions were recorded/i,
      ),
    )
    expect(screen.getByTestId('warehouse-grid')).toBeInTheDocument()
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
  })
})
