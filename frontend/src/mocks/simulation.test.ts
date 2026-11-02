import { afterEach, describe, expect, it, vi } from 'vitest'
import { DEMO_RUN_ID } from './verification'
import { mockSimulationAdapter } from './simulation'

describe('mock simulation adapter', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  function enableMocks() {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
  }

  it('fails closed when mocks are disabled', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    await expect(mockSimulationAdapter.getRunSimulation(DEMO_RUN_ID)).rejects.toThrow(
      /VITE_USE_MOCKS/,
    )
  })

  it('serves a deterministic demo recording for the demo run only', async () => {
    enableMocks()
    const first = await mockSimulationAdapter.getRunSimulation(DEMO_RUN_ID)
    const second = await mockSimulationAdapter.getRunSimulation(DEMO_RUN_ID)
    expect(first).not.toBeNull()
    expect(first).toEqual(second)

    expect(first?.environment.run_id).toBe(DEMO_RUN_ID)
    expect(first?.environment.environment_version).toBe('warehouse_v1')
    // Start and goal never overlap obstacles, and stay inside the grid.
    const obstacleKeys = new Set(
      (first?.environment.obstacles ?? []).map((cell) => `${cell.row},${cell.col}`),
    )
    expect(
      obstacleKeys.has(`${first?.environment.start.row},${first?.environment.start.col}`),
    ).toBe(false)
    expect(obstacleKeys.has(`${first?.environment.goal.row},${first?.environment.goal.col}`)).toBe(
      false,
    )
  })

  it('places the fault marker only at the recorded event timestep', async () => {
    enableMocks()
    const replay = await mockSimulationAdapter.getRunSimulation(DEMO_RUN_ID)
    expect(replay?.faultMarkers).toHaveLength(1)
    const marker = replay?.faultMarkers[0]
    expect(marker?.event_id).toBe('evt_demo_step_812')
    expect(marker?.at_timestep).toBe(812)
    // The marker sits exactly on the goal-arrival step, matching the demo
    // incident evidence trail.
    const arrival = replay?.trajectory.find((point) => point.timestep === marker?.at_timestep)
    expect(arrival?.cell).toEqual(replay?.environment.goal)
    expect(arrival?.terminated).toBe(true)
  })

  it('records an episode termination and reset without a timestep discontinuity', async () => {
    enableMocks()
    const replay = await mockSimulationAdapter.getRunSimulation(DEMO_RUN_ID)
    const timesteps = (replay?.trajectory ?? []).map((point) => point.timestep)
    // Monotonic within the recording — resets do not rewind the run counter.
    for (let index = 1; index < timesteps.length; index += 1) {
      expect(timesteps[index]).toBe((timesteps[index - 1] ?? 0) + 1)
    }
    const terminated = replay?.trajectory.filter((point) => point.terminated) ?? []
    expect(terminated).toHaveLength(1)
    expect(terminated[0]?.cell).toEqual(replay?.environment.goal)
  })

  it('never serves fixtures for unknown run ids', async () => {
    enableMocks()
    expect(await mockSimulationAdapter.getRunSimulation('run_unknown')).toBeNull()
  })
})
