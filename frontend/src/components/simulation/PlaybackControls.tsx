import type { CSSProperties } from 'react'
import type { PlaybackControls as PlaybackMachine } from '../../hooks/usePlayback'

/**
 * Playback controls for a recorded timestep window.
 *
 * A native range slider (keyboard-steppable by default) plus play/pause,
 * single-step, and jump controls. Everything is derived from the recordeds
 * window: controls disable at the recorded bounds, stepping pauses automatic
 * advance, and the slider snaps to recorded timesteps only — no positions
 * beyond the recording can be reached.
 */
interface PlaybackControlsProps {
  min: number
  max: number
  controls: PlaybackMachine
}

const buttonStyle: CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 'var(--space-1)',
  padding: '4px 10px',
  border: '1px solid var(--border-primary)',
  borderRadius: 'var(--radius-sm)',
  background: 'transparent',
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-sans)',
  fontSize: 'var(--text-xs)',
  cursor: 'pointer',
}

const disabledStyle: CSSProperties = {
  color: 'var(--text-muted)',
  borderColor: 'var(--border-secondary)',
  cursor: 'default',
}

function ControlButton({
  label,
  onClick,
  disabled,
  glyph,
}: {
  label: string
  onClick: () => void
  disabled?: boolean
  glyph: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      style={{ ...buttonStyle, ...(disabled ? disabledStyle : null), minWidth: '34px' }}
    >
      <span aria-hidden="true">{glyph}</span>
    </button>
  )
}

export function PlaybackControls({ min, max, controls }: PlaybackControlsProps) {
  return (
    <div
      data-testid="playback-controls"
      style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', flexWrap: 'wrap' }}
    >
      <ControlButton
        label="Jump to start"
        onClick={controls.jumpToStart}
        disabled={controls.atStart}
        glyph="|◀"
      />
      <ControlButton
        label="Step back one recorded timestep"
        onClick={controls.stepBack}
        disabled={controls.atStart}
        glyph="◀|"
      />
      {controls.playing ? (
        <ControlButton label="Pause playback" onClick={controls.pause} glyph="⏸" />
      ) : (
        <ControlButton
          label="Play from current timestep"
          onClick={controls.play}
          disabled={controls.atEnd}
          glyph="▶"
        />
      )}
      <ControlButton
        label="Step forward one recorded timestep"
        onClick={controls.stepForward}
        disabled={controls.atEnd}
        glyph="▶|"
      />
      <ControlButton
        label="Jump to end"
        onClick={controls.jumpToEnd}
        disabled={controls.atEnd}
        glyph="⏭"
      />

      <input
        type="range"
        min={min}
        max={max}
        step={1}
        value={controls.timestep}
        onChange={(event) => controls.goTo(Number(event.target.value))}
        aria-label="Playback timestep"
        aria-valuetext={`Timestep ${controls.timestep} of ${max}`}
        data-testid="playback-slider"
        style={{ flex: 1, minWidth: '160px', accentColor: 'var(--text-primary)' }}
      />

      <span
        data-testid="playback-status"
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 'var(--text-xs)',
          color: 'var(--text-secondary)',
          whiteSpace: 'nowrap',
        }}
      >
        Timestep {controls.timestep} / {max}
      </span>
    </div>
  )
}
