import type { ReactNode } from 'react'
import { SPEED_OPTIONS, primaryAction, type ControlAvailability } from './studioConfig'
import type { SessionCommand } from '../../services/studio'
import type { SessionStatus } from './studioTypes'

export type ViewMode = '3d' | '2d'

interface Props {
  availability: ControlAvailability
  status: SessionStatus | null
  pendingCommand: 'pause' | null
  busy: string | null
  speed: number
  /** Why Initialize is unavailable (shown as a hint), or null. */
  initializeHint: string | null
  viewMode: ViewMode
  webgl: boolean
  onInitialize: () => void
  onCommand: (command: SessionCommand) => void
  onSpeed: (speed: number) => void
  onResetCamera: () => void
  onViewModeChange: (mode: ViewMode) => void
  manual: { available: boolean; active: boolean; hint: string | null }
  onToggleManual: () => void
}

function Spinner() {
  return <span className="spinner" aria-hidden="true" />
}

/**
 * Training lifecycle controls (left) and viewport controls (right), separated
 * by a divider. Availability mirrors the backend state machine.
 */
export function ControlToolbar({
  availability,
  status,
  pendingCommand,
  busy,
  speed,
  initializeHint,
  viewMode,
  webgl,
  onInitialize,
  onCommand,
  onSpeed,
  onResetCamera,
  onViewModeChange,
  manual,
  onToggleManual,
}: Props) {
  const idle = busy === null
  const label = pendingCommand === 'pause' ? 'pausing…' : (status ?? 'no session')
  const primary = primaryAction(status, availability)
  const cls = (name: NonNullable<ReturnType<typeof primaryAction>> | 'other') =>
    name === primary ? 'btn btn--primary' : 'btn btn--ghost'

  const labelled = (running: string, text: ReactNode, command: string) =>
    busy === command ? (
      <>
        <Spinner />
        {running}
      </>
    ) : (
      text
    )

  return (
    <div className="control-bar" role="toolbar" aria-label="Training controls">
      <div
        className="control-bar__group control-bar__group--training"
        role="group"
        aria-label="Training"
      >
        <button
          type="button"
          className={cls('initialize')}
          disabled={!availability.initialize || !idle}
          onClick={onInitialize}
          title={initializeHint ?? 'Create the sandbox for the selected agent and environment'}
        >
          {labelled('Initializing…', 'Initialize', 'initialize')}
        </button>
        <button
          type="button"
          className={cls('train')}
          disabled={!availability.train || !idle}
          onClick={() => onCommand('start')}
        >
          {labelled('Starting…', 'Train', 'start')}
        </button>
        <button
          type="button"
          className={cls('pause')}
          disabled={!availability.pause || !idle}
          onClick={() => onCommand('pause')}
          title="Pause (Space)"
        >
          {labelled('Pausing…', 'Pause', 'pause')}
        </button>
        <button
          type="button"
          className={cls('resume')}
          disabled={!availability.resume || !idle}
          onClick={() => onCommand('resume')}
          title="Resume (Space)"
        >
          {labelled('Resuming…', 'Resume', 'resume')}
        </button>
        <button
          type="button"
          className="btn btn--danger"
          disabled={!availability.stop || !idle}
          onClick={() => onCommand('stop')}
        >
          {labelled('Stopping…', 'Stop', 'stop')}
        </button>
        <button
          type="button"
          className="btn btn--ghost"
          disabled={!availability.reset || !idle}
          onClick={() => onCommand('reset')}
          title="Discard this run's metrics and rebuild the environment"
        >
          {labelled('Resetting…', 'Reset', 'reset')}
        </button>
        <button
          type="button"
          className={`btn btn--ghost${manual.active ? ' is-active' : ''}`}
          aria-pressed={manual.active}
          disabled={!manual.available || !idle}
          onClick={onToggleManual}
          title={
            manual.hint
              ? `Take over the agent with the keyboard: ${manual.hint}`
              : 'This environment has no keyboard mapping for manual control'
          }
        >
          {manual.active ? 'Release control' : 'Take control'}
        </button>
      </div>

      <span className="control-bar__spacer" />

      <div
        className="control-bar__group control-bar__group--viewport"
        role="group"
        aria-label="Viewport"
      >
        <label
          htmlFor="sim-speed"
          style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}
        >
          Playback speed
        </label>
        <select
          id="sim-speed"
          value={speed}
          onChange={(e) => onSpeed(Number(e.target.value))}
          title="Paces the simulation for viewing. It does not change the learning algorithm."
        >
          {SPEED_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn btn--ghost"
          onClick={onResetCamera}
          title="Reset camera (C)"
        >
          Reset camera
        </button>
        <div className="seg" role="group" aria-label="Render mode">
          {(['3d', '2d'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              aria-pressed={viewMode === mode}
              disabled={mode === '3d' && !webgl}
              title={mode === '3d' && !webgl ? 'WebGL is not available in this browser' : undefined}
              onClick={() => onViewModeChange(mode)}
            >
              {mode.toUpperCase()}
            </button>
          ))}
        </div>
        <span
          className="status-pill"
          data-status={status ?? 'none'}
          role="status"
          aria-live="polite"
        >
          {label}
        </span>
      </div>
    </div>
  )
}
