/**
 * Keyboard mappings for manual control. Action numbers follow the backend
 * environments: CartPole 0 = push left, 1 = push right; warehouse grid
 * 0 = up, 1 = down, 2 = left, 3 = right.
 */
const LEFT_RIGHT: Record<string, number> = {
  ArrowLeft: 0,
  a: 0,
  A: 0,
  ArrowRight: 1,
  d: 1,
  D: 1,
}

const GRID: Record<string, number> = {
  ArrowUp: 0,
  w: 0,
  W: 0,
  ArrowDown: 1,
  s: 1,
  S: 1,
  ArrowLeft: 2,
  a: 2,
  A: 2,
  ArrowRight: 3,
  d: 3,
  D: 3,
}

const KEY_MAPS: Record<string, Record<string, number>> = {
  cartpole: LEFT_RIGHT,
  grid_maze: GRID,
}

const HINTS: Record<string, string> = {
  cartpole: '← / A push left · → / D push right',
  grid_maze: '↑ W up · ↓ S down · ← A left · → D right',
}

/** The action a key triggers in an environment, or null when the key is unmapped. */
export function actionForKey(renderer: string | null, key: string): number | null {
  if (renderer === null) return null
  const map = KEY_MAPS[renderer]
  return map && key in map ? map[key] : null
}

/** On-screen help for the controls, or null when the environment has no keyboard mapping. */
export function controlHint(renderer: string | null): string | null {
  return renderer !== null ? (HINTS[renderer] ?? null) : null
}
