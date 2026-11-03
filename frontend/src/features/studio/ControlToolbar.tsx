import { SPEED_OPTIONS, type ControlAvailability } from './studioConfig'
import type { SessionCommand } from '../../services/studio'
import type { SessionStatus } from './studioTypes'

interface Props {
  availability: ControlAvailability
  status: SessionStatus | null
  pendingCommand: 'pause' | null
  busy: string | null
  speed: number
  /** Why Initialize is unavailable (shown as a hint), or null. */
  initializeHint: string | null
  onInitialize: () => void
  onCommand: (command: SessionCommand) => void
  onSpeed: (speed: number) => void
  onResetCamera: () => void
}

/** Training lifecycle controls. Availability mirrors the backend state machine. */
export function ControlToolbar({
  availability,
  status,
  pendingCommand,
  busy,
  speed,
  initializeHint,
  onInitialize,
  onCommand,
  onSpeed,
  onResetCamera,
}: Props) {
  const idle = busy === null
  const label = pendingCommand === 'pause' ? 'pausing…' : (status ?? 'no session')
  return (
    <div className="control-bar" role="toolbar" aria-label="Training controls">
      <button type="button" className="btn btn--ghost" disabled={!availability.initialize || !idle} onClick={onInitialize} title={initializeHint ?? 'Create the sandbox for the selected agent and environment'}>
        {busy === 'initialize' ? 'Initializing…' : 'Initialize'}
      </button>
      <button type="button" className="btn" disabled={!availability.train || !idle} onClick={() => onCommand('start')}>
        Train
      </button>
      <button type="button" className="btn btn--ghost" disabled={!availability.pause || !idle} onClick={() => onCommand('pause')}>
        Pause
      </button>
      <button type="button" className="btn btn--ghost" disabled={!availability.resume || !idle} onClick={() => onCommand('resume')}>
        Resume
      </button>
      <button type="button" className="btn btn--danger" disabled={!availability.stop || !idle} onClick={() => onCommand('stop')}>
        Stop
      </button>
      <button type="button" className="btn btn--ghost" disabled={!availability.reset || !idle} onClick={() => onCommand('reset')} title="Discard this run's metrics and rebuild the environment">
        Reset
      </button>

      <span className="control-bar__spacer" />

      <label htmlFor="sim-speed" style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>
        Playback speed
      </label>
      <select id="sim-speed" value={speed} onChange={(e) => onSpeed(Number(e.target.value))} title="Paces the simulation for viewing. It does not change the learning algorithm.">
        {SPEED_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
      <button type="button" className="btn btn--ghost" onClick={onResetCamera}>
        Reset camera
      </button>
      <span className="status-pill" data-status={status ?? 'none'} role="status" aria-live="polite">
        {label}
      </span>
    </div>
  )
}
