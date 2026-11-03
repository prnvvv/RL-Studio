/**
 * Simulation state adapters: translate the renderer-neutral backend frame into
 * the poses a scene needs. Pure functions; no rendering and no learning logic.
 */
import type { FramePayload } from './studioTypes'

export interface CartPoleScene {
  x_limit: number
  theta_limit: number
  pole_length: number
}

export interface CartPolePose {
  cartX: number
  /** Positive leans toward +x. Radians. */
  poleAngle: number
  atLimit: boolean
}

const CARTPOLE_FALLBACK: CartPoleScene = { x_limit: 2.4, theta_limit: 0.2095, pole_length: 1 }

export function cartPoleScene(scene: Record<string, unknown> | null): CartPoleScene {
  const s = (scene ?? {}) as Partial<CartPoleScene>
  return {
    x_limit: typeof s.x_limit === 'number' ? s.x_limit : CARTPOLE_FALLBACK.x_limit,
    theta_limit: typeof s.theta_limit === 'number' ? s.theta_limit : CARTPOLE_FALLBACK.theta_limit,
    pole_length: typeof s.pole_length === 'number' ? s.pole_length : CARTPOLE_FALLBACK.pole_length,
  }
}

export function adaptCartPole(frame: FramePayload | null, scene: CartPoleScene): CartPolePose {
  const x = frame?.state.x ?? 0
  const theta = frame?.state.theta ?? 0
  return {
    cartX: x,
    poleAngle: theta,
    atLimit: Math.abs(x) >= scene.x_limit || Math.abs(theta) >= scene.theta_limit,
  }
}

export interface GridScene {
  rows: number
  cols: number
  start: [number, number]
  goal: [number, number]
  obstacles: Array<[number, number]>
}

export function gridScene(scene: Record<string, unknown> | null): GridScene | null {
  const s = scene as Partial<GridScene> | null
  if (!s || typeof s.rows !== 'number' || typeof s.cols !== 'number') return null
  return {
    rows: s.rows,
    cols: s.cols,
    start: s.start ?? [0, 0],
    goal: s.goal ?? [s.rows - 1, s.cols - 1],
    obstacles: s.obstacles ?? [],
  }
}

/** Grid cell (row, col) to world-plane coordinates centred on the grid. */
export function cellToWorld(grid: GridScene, row: number, col: number): [number, number] {
  return [col - (grid.cols - 1) / 2, row - (grid.rows - 1) / 2]
}

export function adaptGridAgent(frame: FramePayload | null, grid: GridScene): [number, number] {
  const row = frame?.state.row ?? grid.start[0]
  const col = frame?.state.col ?? grid.start[1]
  return [row, col]
}
