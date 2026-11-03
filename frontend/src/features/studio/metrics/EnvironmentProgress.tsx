import { formatInt, formatNumber } from '../format'
import type { StudioStore } from '../studioStore'
import type { Progress } from '../studioTypes'
import { useFrameSnapshot } from '../useFrameSnapshot'

/**
 * Where the current episode is: step against the episode limit, collisions so far, and the
 * distance to the goal for navigation environments. All values come from the live frame and the
 * backend's progress events.
 */
export function EnvironmentProgress({
  store,
  progress,
  maxSteps,
}: {
  store: StudioStore
  progress: Progress
  maxSteps: number | null
}) {
  const frame = useFrameSnapshot(store)
  const step = frame ? Math.max(0, frame.episode_step) : 0
  const distance = frame?.state.distance_to_goal ?? progress.env_state?.distance_to_goal
  const hasDistance = typeof distance === 'number'
  return (
    <div className="env-progress">
      {maxSteps !== null && (
        <div>
          <div className="env-progress__row">
            <span>Episode step</span>
            <strong>
              {formatInt(step)} / {formatInt(maxSteps)}
            </strong>
          </div>
          <div
            className="progress-bar"
            role="progressbar"
            aria-label="Episode step"
            aria-valuemin={0}
            aria-valuemax={maxSteps}
            aria-valuenow={Math.min(step, maxSteps)}
          >
            <div style={{ width: `${Math.min(1, step / Math.max(maxSteps, 1)) * 100}%` }} />
          </div>
        </div>
      )}
      <div className="tiles">
        <div className="tile">
          <span>Collisions</span>
          <strong>{formatInt(progress.collisions)}</strong>
        </div>
        {hasDistance && (
          <div className="tile">
            <span>Distance to goal</span>
            <strong>{formatNumber(distance, 0)}</strong>
          </div>
        )}
        <div className="tile">
          <span>Episode reward</span>
          <strong>{formatNumber(frame ? frame.episode_reward : null)}</strong>
        </div>
      </div>
    </div>
  )
}
