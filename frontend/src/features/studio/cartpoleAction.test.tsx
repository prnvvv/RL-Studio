import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CartPole2D } from './renderers/CartPole2D'
import type { ScenePalette } from './renderers/palette'
import { cartPoleActionDirection } from './simulationAdapters'
import { StudioStore } from './studioStore'
import type { FramePayload } from './studioTypes'

const palette: ScenePalette = {
  background: '#000',
  floor: '#111',
  grid: '#222',
  structure: '#555',
  agent: '#fff',
  accent: '#bbb',
  good: '#0f0',
  bad: '#f00',
  text: '#aaa',
}
const scene = { x_limit: 2.4, theta_limit: 0.2, pole_length: 1 }

const frame = (overrides: Partial<FramePayload> = {}): FramePayload => ({
  timestep: 5,
  episode: 1,
  episode_step: 5,
  action: 1,
  reward: 1,
  episode_reward: 5,
  collision: false,
  disturbance: false,
  done: false,
  state: { x: 0.5, x_dot: 0, theta: 0.01, theta_dot: 0 },
  ...overrides,
})

describe('cartPoleActionDirection', () => {
  it('maps the discrete actions to push directions', () => {
    expect(cartPoleActionDirection(frame({ action: 0 }))).toBe(-1)
    expect(cartPoleActionDirection(frame({ action: 1 }))).toBe(1)
  })

  it('reports no push without a real action', () => {
    expect(cartPoleActionDirection(null)).toBe(0)
    expect(cartPoleActionDirection(frame({ action: null }))).toBe(0)
    expect(cartPoleActionDirection(frame({ action: [0.3] }))).toBe(0)
    expect(cartPoleActionDirection(frame({ initial: true }))).toBe(0)
  })
})

describe('CartPole2D action arrow', () => {
  it('draws an arrow in the pushed direction and none for the initial preview', () => {
    const store = new StudioStore()
    store.applyFrame(frame({ action: 0 }))
    const { unmount } = render(<CartPole2D scene={scene} store={store} palette={palette} />)
    expect(screen.getByTestId('action-arrow').getAttribute('transform')).toContain('scale(-1 1)')
    unmount()

    const preview = new StudioStore()
    preview.applyFrame(frame({ initial: true }))
    render(<CartPole2D scene={scene} store={preview} palette={palette} />)
    expect(screen.queryByTestId('action-arrow')).toBeNull()
  })
})
