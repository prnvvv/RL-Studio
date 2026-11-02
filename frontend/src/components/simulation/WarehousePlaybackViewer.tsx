import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { SimulationReplay } from '../../schemas/simulation'
import type { SimulationService } from '../../services/simulation'
import { createSimulationService } from '../../services/simulation'
import { useServiceQuery } from '../../hooks/useServiceQuery'
import { usePlayback } from '../../hooks/usePlayback'
import { DEFAULT_DISPLAY_OPTIONS, type WarehouseDisplayOptions } from './displayOptions'
import { MOCK_DATA_LABEL, type MockData, unwrapMockData } from '../../mocks'
import { findLayoutIssues, findTrajectoryIssues } from '../../utils/warehouse'
import { EmptyState } from '../ui/EmptyState'
import { ErrorState } from '../ui/ErrorState'
import { LoadingSkeleton } from '../ui/LoadingSkeleton'
import { StatusBadge } from '../ui/StatusBadge'
import { WarehouseGridView } from './WarehouseGridView'
import { PlaybackControls } from './PlaybackControls'

/**
 * Composed playback view for one run's recorded simulation replay.
 *
 * Honest-state rules:
 * - Loading, not-found, and error states are explicit; only a GET is ever
 *   retried, so the retry affordance is always safe here.
 * - Recorded layout problems block rendering entirely (an unusable layout
 *   must not be drawn into something plausible-looking).
 * - Trajectory problems are reported beside the grid; points the record
 *   places outside the grid are never silently clipped or drawn.
 * - Fixture-backed payloads keep their visible `Sample data` label.
 * - Display toggles are view preferences only; they never mutate data.
 */
export function WarehousePlaybackViewer({
  runId,
  service,
  fallback,
  title,
}: {
  /** The run whose recorded replay is displayed. */
  runId: string
  /** Service injection for tests; defaults to the real service selection. */
  service?: SimulationService
  /** Rendered when no replay exists for the run (e.g. the static illustration). */
  fallback?: ReactNode
  title?: string
}) {
  const resolvedService = useMemo(() => service ?? createSimulationService(), [service])
  const query = useServiceQuery(
    () => resolvedService.getRunSimulation(runId),
    [resolvedService, runId],
  )
  const [options, setOptions] = useState<WarehouseDisplayOptions>(DEFAULT_DISPLAY_OPTIONS)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      {title && (
        <h2 style={{ fontSize: 'var(--text-lg)', margin: 0, color: 'var(--text-primary)' }}>
          {title}
        </h2>
      )}
      <WarehouseReplay
        query={query.state}
        runId={runId}
        fallback={fallback}
        options={options}
        onToggle={setOptions}
        reload={query.reload}
      />
    </div>
  )
}

interface ReplayViewProps {
  query: ReturnType<typeof useServiceQuery<SimulationReplay | MockData<SimulationReplay>>>['state']
  runId: string
  fallback?: ReactNode
  options: WarehouseDisplayOptions
  onToggle: (next: WarehouseDisplayOptions) => void
  reload: () => void
}

function WarehouseReplay({ query, runId, fallback, options, onToggle, reload }: ReplayViewProps) {
  if (query.state === 'loading') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        <p
          role="status"
          style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', margin: 0 }}
        >
          Loading recorded simulation replay…
        </p>
        <LoadingSkeleton rows={4} />
      </div>
    )
  }

  if (query.state === 'error') {
    if (query.error.kind === 'not_found') {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <EmptyState
            title="No recorded simulation replay for this run"
            description={`No recorded environment replay is available for run ${runId}. Playback appears here once the backend records episode state; nothing is inferred from training metrics.`}
          />
          {fallback}
        </div>
      )
    }
    return (
      <ErrorState
        title="Recorded simulation replay unavailable"
        description={query.error.message}
        action={
          <button
            type="button"
            onClick={reload}
            style={{
              padding: '4px 12px',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-sm)',
              background: 'transparent',
              color: 'var(--text-primary)',
              fontSize: 'var(--text-xs)',
              cursor: 'pointer',
            }}
          >
            Retry loading
          </button>
        }
      />
    )
  }

  const labeled = 'label' in query.data
  const replay = unwrapMockData(query.data)
  return <ReplaySurface replay={replay} labeled={labeled} options={options} onToggle={onToggle} />
}

function ReplaySurface({
  replay,
  labeled,
  options,
  onToggle,
}: {
  replay: SimulationReplay
  labeled: boolean
  options: WarehouseDisplayOptions
  onToggle: (next: WarehouseDisplayOptions) => void
}) {
  // Layout problems block drawing: an invalid record must never be rendered
  // into a plausible-looking warehouse. The playback hook is called before any
  // early return so hook order stays stable across replays.
  const layoutIssues = useMemo(() => findLayoutIssues(replay.environment), [replay])
  const trajectoryIssues = useMemo(() => findTrajectoryIssues(replay), [replay])

  const trajectory = replay.trajectory
  const minTimestep = trajectory.length > 0 ? trajectory[0].timestep : 0
  const maxTimestep = trajectory.length > 0 ? trajectory[trajectory.length - 1].timestep : 0
  const playback = usePlayback(minTimestep, maxTimestep)

  if (layoutIssues.length > 0) {
    return <AccuracyIssues title="Recorded layout cannot be rendered" issues={layoutIssues} />
  }

  const windowLabel =
    trajectory.length > 0
      ? `Recorded timesteps ${minTimestep}${'\u2013'}${maxTimestep} \u00b7 ${trajectory.length} recorded positions`
      : 'The recording contains no recorded positions'

  return (
    <div
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}
      data-testid="warehouse-replay-surface"
    >
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}
      >
        <span
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {windowLabel}
        </span>
        {labeled && <StatusBadge label={MOCK_DATA_LABEL} tone="quiet" glyph="dot" />}
        <DisplayToggles options={options} onToggle={onToggle} />
      </div>

      {trajectoryIssues.length > 0 && (
        <AccuracyIssues
          title="The recorded trajectory has accuracy issues; unrenderable points are not drawn"
          issues={trajectoryIssues}
        />
      )}

      <WarehouseGridView replay={replay} timestep={playback.timestep} options={options} />
      {trajectory.length > 0 ? (
        <PlaybackControls min={minTimestep} max={maxTimestep} controls={playback} />
      ) : null}

      {trajectory.length === 0 && (
        <p
          role="note"
          style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', margin: 0 }}
        >
          This recording holds the environment layout only; no agent positions were recorded, so
          there is nothing to play back.
        </p>
      )}

      {replay.faultMarkers.length > 0 && (
        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', margin: 0 }}>
          {replay.faultMarkers.length} recorded fault marker
          {replay.faultMarkers.length === 1 ? '' : 's'} shown at their recorded event timesteps.
        </p>
      )}
    </div>
  )
}

/** Display-only checkboxes; mutating them never touches the replay data. */
function DisplayToggles({
  options,
  onToggle,
}: {
  options: WarehouseDisplayOptions
  onToggle: (next: WarehouseDisplayOptions) => void
}) {
  const toggle = (key: keyof WarehouseDisplayOptions, label: string) => (
    <label
      key={key}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-1)',
        fontSize: 'var(--text-xs)',
        color: 'var(--text-secondary)',
      }}
    >
      <input
        type="checkbox"
        checked={options[key]}
        onChange={(event) => onToggle({ ...options, [key]: event.target.checked })}
        style={{ accentColor: 'var(--text-primary)' }}
      />
      {label}
    </label>
  )

  return (
    <div
      role="group"
      aria-label="Display settings"
      style={{ display: 'inline-flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}
    >
      {toggle('showTrajectory', 'Trajectory')}
      {toggle('showAgent', 'Agent')}
      {toggle('showGoal', 'Goal')}
      {toggle('showObstacles', 'Obstacles')}
    </div>
  )
}

function AccuracyIssues({ title, issues }: { title: string; issues: string[] }) {
  return (
    <div
      role="note"
      aria-label={title}
      style={{
        border: '1px dashed var(--border-primary)',
        borderRadius: 'var(--radius-sm)',
        padding: 'var(--space-2) var(--space-3)',
        color: 'var(--text-secondary)',
        fontSize: 'var(--text-xs)',
      }}
    >
      <p style={{ margin: '0 0 4px', color: 'var(--text-primary)' }}>{title}</p>
      <ul style={{ margin: 0, paddingLeft: '18px' }}>
        {issues.map((issue) => (
          <li key={issue}>{issue}</li>
        ))}
      </ul>
    </div>
  )
}
