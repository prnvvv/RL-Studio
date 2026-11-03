import { useEffect, useRef, useState } from 'react'
import { InfoTip } from './InfoTip'
import { CHAOS_KIND_LABELS } from './studioConfig'
import type { ChaosState } from './studioTypes'

const COMMIT_DELAY_MS = 250

interface Props {
  /** Disturbances this environment supports (from the backend catalog). */
  kinds: string[]
  chaos: ChaosState
  /** False until a live session exists. */
  available: boolean
  /** Triggering needs a running session. */
  canTrigger: boolean
  onChange: (patch: { enabled?: boolean; intensity?: number; kinds?: string[] }) => void
  onTrigger: (kind: string) => void
}

/** Runtime chaos controls: everything here acts on the live session through the backend. */
export function ChaosPanel({ kinds, chaos, available, canTrigger, onChange, onTrigger }: Props) {
  const [intensity, setIntensity] = useState(chaos.intensity)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => setIntensity(chaos.intensity), [chaos.intensity])
  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current)
    },
    [],
  )

  if (kinds.length === 0) {
    return <p className="note">This environment does not support chaos mode.</p>
  }

  const slide = (value: number) => {
    setIntensity(value)
    if (timer.current !== null) clearTimeout(timer.current)
    timer.current = setTimeout(() => onChange({ intensity: value }), COMMIT_DELAY_MS)
  }
  const toggleKind = (kind: string, on: boolean) =>
    onChange({
      kinds: on ? [...new Set([...chaos.kinds, kind])] : chaos.kinds.filter((k) => k !== kind),
    })

  return (
    <div className="chaos-panel">
      {!available && (
        <p className="note">
          Initialize a session to use chaos mode. These controls act on the running simulation.
        </p>
      )}
      <div className="field">
        <span className="field__label">
          <label htmlFor="chaos-enabled">Chaos mode</label>
          <InfoTip label="About chaos mode">
            Randomly injects the selected disturbances while the agent trains, and logs each one
            under the FAULT category. Disturbed steps are marked in the stored trajectory.
          </InfoTip>
        </span>
        <input
          id="chaos-enabled"
          type="checkbox"
          checked={chaos.enabled}
          disabled={!available}
          onChange={(event) => onChange({ enabled: event.target.checked })}
        />
      </div>
      <div className="field">
        <span className="field__label">
          <label htmlFor="chaos-intensity">Intensity</label>
          <InfoTip label="About chaos intensity">
            Scales how often disturbances strike and how strong they are, from 0 (none) to 1
            (maximum).
          </InfoTip>
          <output htmlFor="chaos-intensity" className="chaos-panel__value">
            {intensity.toFixed(2)}
          </output>
        </span>
        <input
          id="chaos-intensity"
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={intensity}
          disabled={!available}
          onChange={(event) => slide(Number(event.target.value))}
        />
      </div>
      <fieldset className="chaos-panel__kinds" disabled={!available}>
        <legend>Disturbances</legend>
        {kinds.map((kind) => {
          const meta = CHAOS_KIND_LABELS[kind] ?? { label: kind, help: kind }
          return (
            <div key={kind} className="chaos-panel__kind">
              <label>
                <input
                  type="checkbox"
                  checked={chaos.kinds.includes(kind)}
                  onChange={(event) => toggleKind(kind, event.target.checked)}
                />{' '}
                {meta.label}
              </label>
              <InfoTip label={`About ${meta.label}`}>{meta.help}</InfoTip>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={!canTrigger}
                onClick={() => onTrigger(kind)}
                title="Inject one now, even with chaos mode off"
              >
                Trigger now
              </button>
            </div>
          )
        })}
      </fieldset>
      <p className="note" role="status">
        Injected so far: {chaos.events} disturbance{chaos.events === 1 ? '' : 's'}
        {chaos.noise_steps > 0 ? ` · sensor noise on ${chaos.noise_steps} steps` : ''}.
      </p>
    </div>
  )
}
