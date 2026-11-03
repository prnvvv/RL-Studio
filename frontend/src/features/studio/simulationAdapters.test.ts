import { describe, expect, it } from 'vitest'
import { adaptCartPole, adaptGridAgent, cartPoleScene, cellToWorld, gridScene } from './simulationAdapters'
import type { FramePayload } from './studioTypes'

const frame = (state: Record<string, number>): FramePayload => ({
  timestep: 1, episode: 1, episode_step: 1, action: 0, reward: 1, episode_reward: 1,
  collision: false, disturbance: false, done: false, state,
})

describe('simulation adapters', () => {
  it('maps cartpole state to a pose and flags limit crossings', () => {
    const scene = cartPoleScene({ x_limit: 2.4, theta_limit: 0.2, pole_length: 1 })
    expect(adaptCartPole(frame({ x: 1, theta: 0.1 }), scene)).toEqual({ cartX: 1, poleAngle: 0.1, atLimit: false })
    expect(adaptCartPole(frame({ x: 0, theta: 0.3 }), scene).atLimit).toBe(true)
    expect(adaptCartPole(null, scene).cartX).toBe(0)
  })

  it('falls back to documented cartpole limits when the scene is absent', () => {
    expect(cartPoleScene(null).x_limit).toBe(2.4)
  })

  it('rejects scenes that are not grids and centres cells', () => {
    expect(gridScene({})).toBeNull()
    const grid = gridScene({ rows: 6, cols: 4, start: [0, 0], goal: [5, 3], obstacles: [] })!
    expect(cellToWorld(grid, 0, 0)).toEqual([-1.5, -2.5])
    expect(adaptGridAgent(frame({ row: 2, col: 3 }), grid)).toEqual([2, 3])
    expect(adaptGridAgent(null, grid)).toEqual([0, 0])
  })
})
