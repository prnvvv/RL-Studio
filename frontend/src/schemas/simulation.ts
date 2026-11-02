/**
 * Warehouse simulation & trajectory contracts — @planned.
 *
 * Mirrors the coordinates and invariants of Person 2's environment
 * (`backend/environments/config.py` `WarehouseConfig`, `warehouse_env.py`
 * `Warehouse2DEnv`): a `rows x cols` bounded grid, 4-connectivity, `start` and
 * `goal` as `(row, col)` cells inside the grid, and obstacle cells never
 * overlapping `start`/`goal`.
 *
 * The environment-state endpoints do not exist yet (Person 2 owns run state;
 * the Person 4 provenance setup may expose recorded episode data). These
 * @planned shapes bind the visual-debugging viewers ahead of that contract;
 * keep in sync exactly once the shared schema is published.
 *
 * Honesty rules baked in:
 * - Trajectory positions are recorded points only. The view renders what the
 *   record contains — never interpolated positions.
 * - Fault markers are placed only at recorded fault-injection event positions;
 *   a marker carries the source event id it was derived from.
 * - The frontend renders state; it never authors environment state.
 */
import type { ISODateTime } from './shared'

/** One cell of the warehouse grid, zero-indexed, `(row, col)`. */
export interface WarehouseCell {
  row: number
  col: number
}

/** `WarehouseConfig` view as rendered on the simulation surface. */
export interface WarehouseEnvironmentSnapshot {
  /** @planned environment record lookup. */
  environment_id: string
  environment_version: string
  rows: number
  cols: number
  start: WarehouseCell
  goal: WarehouseCell
  obstacles: WarehouseCell[]
  /** Run the snapshot belongs to, when bound to a recorded run. */
  run_id: string | null
  episode_id: string | null
  /** Wall-clock recording time, when the backend supplies one. */
  snapshot_at: ISODateTime | null
  schema_version: string
}

/**
 * A recorded agent position. `timestep` is the environment's own counter, so
 * playback scrubbing is always in recorded timesteps (possibly starting above
 * zero when a recording covers a later training window).
 */
export interface TrajectoryPoint {
  timestep: number
  cell: WarehouseCell
  /** Whether the recorded record marks this step as episode-terminating. */
  terminated: boolean
}

/**
 * A fault-injection marker. `at_timestep` and `event_id` both come from the
 * recorded event trail — a viewer must never position a marker where no
 * event was recorded.
 */
export interface FaultMarker {
  event_id: string
  at_timestep: number
  /** Stable fault category, e.g. `reward_scale_mismatch`. */
  fault_type: string
  /** Optional human label supplied by the record. */
  label: string | null
}

/** A replayable recording: environment layout + trajectory + fault markers. */
export interface SimulationReplay {
  environment: WarehouseEnvironmentSnapshot
  /** Ascending `timestep`. May start above zero (partial recording). */
  trajectory: TrajectoryPoint[]
  faultMarkers: FaultMarker[]
  run_id: string | null
  schema_version: string
}
