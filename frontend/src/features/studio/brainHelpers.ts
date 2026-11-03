import type { BrainCell, BrainPayload } from './studioTypes'

/** Action names per renderer, in backend action order. */
export const ACTION_LABELS: Record<string, string[]> = {
  cartpole: ['Push left', 'Push right'],
  grid_maze: ['Up', 'Down', 'Left', 'Right'],
}

/** SVG rotation (degrees clockwise from "up") of the arrow for each grid action. */
export const GRID_ARROW_DEGREES = [0, 180, 270, 90]

/** Y-rotation (radians) of a +Z-pointing 3D arrow for each grid action: up, down, left, right. */
export const GRID_ARROW_RADIANS = [Math.PI, 0, -Math.PI / 2, Math.PI / 2]

export function actionLabels(renderer: string | null, count: number): string[] {
  const known = renderer !== null ? ACTION_LABELS[renderer] : undefined
  return Array.from({ length: count }, (_, i) => known?.[i] ?? `Action ${i}`)
}

/** Confidence in the preferred action: the largest probability, or null when there is none. */
export function confidence(probs: number[] | undefined): number | null {
  return probs && probs.length > 0 ? Math.max(...probs) : null
}

/**
 * Opacity of a heat cell from the agent's confidence. A uniform policy (1 / n)
 * maps to the faintest value and a certain one to the strongest, so cells where
 * the agent has no preference stay visually quiet.
 */
export function heatOpacity(probs: number[], min = 0.08, max = 0.8): number {
  const top = confidence(probs) ?? 0
  const floor = 1 / Math.max(probs.length, 1)
  const t = Math.min(1, Math.max(0, (top - floor) / (1 - floor || 1)))
  return min + (max - min) * t
}

export function cellKey(row: number, col: number): string {
  return `${row},${col}`
}

export function gridLookup(cells: BrainCell[] | undefined): Map<string, BrainCell> {
  return new Map((cells ?? []).map((cell) => [cellKey(cell.row, cell.col), cell]))
}

/** Probabilities to show for a brain payload (Gaussian policies have none). */
export function brainProbabilities(brain: BrainPayload | null | undefined): number[] | null {
  return brain?.probs ?? null
}
