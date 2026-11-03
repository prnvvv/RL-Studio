/**
 * Pixel sizes of the three-zone workspace: configuration (left), simulation (center, takes the
 * rest) and metrics (right). Pure functions so the rules are testable without a browser.
 */
export interface WorkspaceLayout {
  left: number
  metrics: number
  /** Height of the logs/experiments dock under the simulation. */
  dock: number
}

// v3: the metrics panel became its own zone; earlier layouts had no `metrics` size.
export const LAYOUT_KEY = 'rl-studio-workspace-layout-v3'

/** No zone can be dragged below these, so nothing collapses out of reach. */
export const MIN_LEFT = 280
export const MIN_METRICS = 280
export const MIN_CENTER = 360
export const MIN_DOCK = 120

/** Below this width the metrics zone becomes a drawer instead of a column. */
export const DRAWER_BREAKPOINT = 1200

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)

/** Keep every zone within its minimum and leave the simulation its minimum width. */
export function clampLayout(layout: WorkspaceLayout, viewportWidth: number): WorkspaceLayout {
  const cap = viewportWidth * 0.5
  let left = clamp(layout.left, MIN_LEFT, Math.max(cap, MIN_LEFT))
  let metrics = clamp(layout.metrics, MIN_METRICS, Math.max(cap, MIN_METRICS))
  const over = left + metrics - (viewportWidth - MIN_CENTER)
  if (over > 0) {
    // Give the room back to the simulation: shrink the metrics zone first, then the left one.
    const fromMetrics = Math.min(over, metrics - MIN_METRICS)
    metrics -= fromMetrics
    left -= Math.min(over - fromMetrics, left - MIN_LEFT)
  }
  return {
    left: Math.round(left),
    metrics: Math.round(metrics),
    dock: Math.max(layout.dock, MIN_DOCK),
  }
}

/** About 30% / 40% / 30% across the viewport. */
export function defaultLayout(viewportWidth: number): WorkspaceLayout {
  return clampLayout(
    { left: viewportWidth * 0.3, metrics: viewportWidth * 0.3, dock: 260 },
    viewportWidth,
  )
}

export function loadLayout(viewportWidth: number): WorkspaceLayout {
  try {
    const raw = window.localStorage.getItem(LAYOUT_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<WorkspaceLayout>
      if (
        typeof parsed.left === 'number' &&
        typeof parsed.metrics === 'number' &&
        typeof parsed.dock === 'number'
      ) {
        return clampLayout(parsed as WorkspaceLayout, viewportWidth)
      }
    }
  } catch {
    // Storage unavailable or corrupt: fall back to the defaults.
  }
  return defaultLayout(viewportWidth)
}

export function saveLayout(layout: WorkspaceLayout): void {
  try {
    window.localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout))
  } catch {
    // Persisting the layout is a convenience only.
  }
}
