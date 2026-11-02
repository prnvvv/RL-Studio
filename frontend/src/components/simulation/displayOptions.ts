/**
 * Display-only toggle state for warehouse simulation viewers.
 *
 * Kept in a separate (non-component) module so component files stay under the
 * react-refresh single-export rule while still sharing the toggle contract
 * between the grid, the playback viewer, and their tests.
 *
 * Toggles are VIEW preferences only: they never mutate replay data and never
 * alter backend state.
 */
export interface WarehouseDisplayOptions {
  /** Show the agent position marker at the playback cursor. */
  showAgent: boolean
  /** Show the goal-cell marker. */
  showGoal: boolean
  /** Show recorded obstacle cells. */
  showObstacles: boolean
  /** Show the recorded trajectory walked up to the playback cursor. */
  showTrajectory: boolean
}

export const DEFAULT_DISPLAY_OPTIONS: WarehouseDisplayOptions = {
  showAgent: true,
  showGoal: true,
  showObstacles: true,
  showTrajectory: true,
}
