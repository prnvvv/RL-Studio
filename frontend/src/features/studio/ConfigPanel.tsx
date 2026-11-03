import { useEffect, useState, type ReactNode } from 'react'
import { InfoTip } from './InfoTip'
import { paramExplanation, paramFacts } from './paramHelp'
import {
  findAgent,
  findEnvironment,
  validateParam,
  type Draft,
  type FieldErrors,
} from './studioConfig'
import type { Catalog, ParamSpec, ParamValue, ParamValues } from './studioTypes'

/** Settings that only apply when the agent learns; hidden for uploaded (inference-only) models. */
const LEARNING_ONLY = new Set(['checkpoint_every', 'eval_every', 'eval_episodes', 'device'])

interface FieldProps {
  spec: ParamSpec
  value: ParamValue | undefined
  error: string | undefined
  disabled: boolean
  /** Also offer a slider for bounded numbers (environment dynamics). */
  slider?: boolean
  onChange: (value: ParamValue) => void
}

function ParamField({ spec, value, error, disabled, slider, onChange }: FieldProps) {
  const id = `cfg-${spec.key}`
  // Numeric fields keep the typed text so partial input ("0.") is not clamped away.
  const [text, setText] = useState(String(value ?? ''))
  useEffect(() => {
    if (spec.kind === 'int' || spec.kind === 'float') {
      setText((current) => (Number(current) === value ? current : String(value ?? '')))
    }
  }, [value, spec.kind])

  let control: ReactNode
  if (spec.kind === 'choice') {
    control = (
      <select
        id={id}
        value={String(value)}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {spec.options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    )
  } else if (spec.kind === 'bool') {
    control = (
      <input
        id={id}
        type="checkbox"
        checked={value === true}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
    )
  } else {
    const bounded =
      slider === true &&
      spec.min !== null &&
      spec.max !== null &&
      Number.isFinite(spec.min) &&
      Number.isFinite(spec.max)
    const numeric = Number(value)
    const slide = bounded ? (
      <input
        type="range"
        className="field__slider"
        aria-label={`${spec.label} slider`}
        min={spec.min ?? undefined}
        max={spec.max ?? undefined}
        step={spec.step ?? 'any'}
        value={Number.isFinite(numeric) ? numeric : (spec.min ?? 0)}
        disabled={disabled}
        onChange={(e) => {
          setText(e.target.value)
          onChange(Number(e.target.value))
        }}
      />
    ) : null
    control = (
      <>
        {slide}
        <input
          id={id}
          type="number"
          inputMode="decimal"
          value={text}
          min={spec.min ?? undefined}
          max={spec.max ?? undefined}
          step={spec.step ?? 'any'}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-err` : undefined}
          onChange={(e) => {
            setText(e.target.value)
            onChange(e.target.value === '' ? ('' as ParamValue) : Number(e.target.value))
          }}
        />
      </>
    )
  }
  return (
    <div className="field">
      <span className="field__label">
        <label htmlFor={id}>{spec.label}</label>
        <InfoTip label={`About ${spec.label}`} meta={paramFacts(spec)}>
          {paramExplanation(spec)}
        </InfoTip>
      </span>
      {control}
      {error && (
        <span id={`${id}-err`} className="field__error" role="alert">
          {error}
        </span>
      )}
    </div>
  )
}

interface SectionProps {
  title: string
  scope: string
  specs: ParamSpec[]
  values: ParamValues
  errors: FieldErrors
  disabled: boolean
  open?: boolean
  sliders?: boolean
  onChange: (key: string, value: ParamValue) => void
  empty?: string
}

function Section({
  title,
  scope,
  specs,
  values,
  errors,
  disabled,
  open,
  sliders,
  onChange,
  empty,
}: SectionProps) {
  return (
    <details className="cfg-section" open={open}>
      <summary>{title}</summary>
      {specs.length === 0 ? (
        <p className="note">{empty ?? 'Nothing to configure.'}</p>
      ) : (
        <div className="cfg-grid">
          {specs.map((spec) => (
            <ParamField
              key={spec.key}
              spec={spec}
              value={values[spec.key]}
              error={
                errors[`${scope}.${spec.key}`] ?? validateParam(spec, values[spec.key]) ?? undefined
              }
              disabled={disabled}
              slider={sliders}
              onChange={(value) => onChange(spec.key, value)}
            />
          ))}
        </div>
      )}
    </details>
  )
}

interface Props {
  catalog: Catalog
  draft: Draft
  errors: FieldErrors
  /** Frozen while a session is active; edits apply on the next initialization. */
  disabled: boolean
  onChange: (
    scope: 'agent_params' | 'env_params' | 'training',
    key: string,
    value: ParamValue,
  ) => void
  /** Runtime environment controls (chaos mode), shown right after the environment settings. */
  environmentExtras?: ReactNode
}

/** Parameter forms generated from the backend's declarative specs. */
export function ConfigPanel({
  catalog,
  draft,
  errors,
  disabled,
  onChange,
  environmentExtras,
}: Props) {
  const agent = findAgent(catalog, draft.agent)
  const env = findEnvironment(catalog, draft.environment)
  const inferenceOnly = agent?.kind === 'custom'
  // Simulation speed is a live playback control (toolbar), not an initialization setting.
  const training = catalog.training_params.filter(
    (spec) => spec.key !== 'simulation_speed' && !(inferenceOnly && LEARNING_ONLY.has(spec.key)),
  )
  return (
    <div>
      {disabled && (
        <p className="note">
          Configuration is locked while a session is active. Reset or stop, then initialize again to
          apply changes.
        </p>
      )}
      {!agent && !env && (
        <p className="note">
          Pick an agent and an environment on the first tab, then tune them here.
        </p>
      )}
      <Section
        title={agent ? `${agent.name} hyperparameters` : 'Agent hyperparameters'}
        scope="agent_params"
        specs={agent?.params ?? []}
        values={draft.agent_params}
        errors={errors}
        disabled={disabled}
        open
        empty={
          inferenceOnly
            ? 'An uploaded model runs inference only: it plays the environment with its stored weights and does not learn, so it has no hyperparameters.'
            : 'Select an agent to configure it.'
        }
        onChange={(k, v) => onChange('agent_params', k, v)}
      />
      <Section
        title={env ? `Environment Dynamics · ${env.name}` : 'Environment Dynamics'}
        scope="env_params"
        specs={env?.params ?? []}
        values={draft.env_params}
        errors={errors}
        disabled={disabled}
        open
        sliders
        empty="Select an environment to configure it."
        onChange={(k, v) => onChange('env_params', k, v)}
      />
      {environmentExtras && (
        <details className="cfg-section" open>
          <summary>Chaos mode</summary>
          <div style={{ padding: 'var(--space-3)' }}>{environmentExtras}</div>
        </details>
      )}
      <Section
        title={inferenceOnly ? 'Run' : 'Training'}
        scope="training"
        specs={training}
        values={draft.training}
        errors={errors}
        disabled={disabled}
        open
        onChange={(k, v) => onChange('training', k, v)}
      />
    </div>
  )
}

/** A titled parameter form, reused for the opponent in Compare mode. */
export { Section as ParamSection }
