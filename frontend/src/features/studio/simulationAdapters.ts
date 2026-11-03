/**
 * Simulation state adapters: translate the renderer-neutral backend frame into
 * the poses a scene needs. Pure functions; no rendering and no learning logic.
 */
import type { FramePayload } from './studioTypes'

/** A numeric state value, or the fallback when the frame is missing or carries something else. */
export function stateNumber(frame: FramePayload | null, key: string, fallback = 0): number {
  const value = frame?.state[key]
  return typeof value === 'number' ? value : fallback
}

/** A list of (x, y) points from the frame state (terrain, obstacle cells), or []. */
export function statePoints(frame: FramePayload | null, key: string): Array<[number, number]> {
  const value = frame?.state[key]
  if (!Array.isArray(value)) return []
  return value.filter(
    (p): p is number[] => Array.isArray(p) && p.length >= 2 && typeof p[0] === 'number',
  ) as Array<[number, number]>
}

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
  const x = stateNumber(frame, 'x')
  const theta = stateNumber(frame, 'theta')
  return {
    cartX: x,
    poleAngle: theta,
    atLimit: Math.abs(x) >= scene.x_limit || Math.abs(theta) >= scene.theta_limit,
  }
}

/**
 * Which way the agent last pushed the cart: -1 (left), 1 (right) or 0 when the
 * frame carries no push (no frame yet, the initial preview, or a non-discrete action).
 * CartPole's discrete actions are 0 = push left and 1 = push right.
 */
export function cartPoleActionDirection(frame: FramePayload | null): -1 | 0 | 1 {
  if (!frame || frame.initial || typeof frame.action !== 'number') return 0
  return frame.action === 1 ? 1 : frame.action === 0 ? -1 : 0
}

export interface GridScene {
  rows: number
  cols: number
  start: [number, number]
  goal: [number, number]
  obstacles: Array<[number, number]>
  /** Obstacles drift; their live cells arrive with each frame. */
  moving_obstacles?: boolean
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
    moving_obstacles: s.moving_obstacles === true,
  }
}

/** Grid cell (row, col) to world-plane coordinates centred on the grid. */
export function cellToWorld(grid: GridScene, row: number, col: number): [number, number] {
  return [col - (grid.cols - 1) / 2, row - (grid.rows - 1) / 2]
}

export function adaptGridAgent(frame: FramePayload | null, grid: GridScene): [number, number] {
  return [stateNumber(frame, 'row', grid.start[0]), stateNumber(frame, 'col', grid.start[1])]
}

/**
 * The obstacle cells to draw now. Static layouts come from the scene; when obstacles move the
 * backend sends their current cells with every frame, and those win.
 */
export function adaptGridObstacles(
  frame: FramePayload | null,
  grid: GridScene,
): Array<[number, number]> {
  const live = statePoints(frame, 'obstacles')
  return grid.moving_obstacles && live.length > 0 ? live : grid.obstacles
}
