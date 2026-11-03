import { useEffect, useState, type ReactNode } from 'react'
import { findAgent, findEnvironment, validateParam, type Draft, type FieldErrors } from './studioConfig'
import type { Catalog, ParamSpec, ParamValue, ParamValues } from './studioTypes'

interface FieldProps {
  spec: ParamSpec
  value: ParamValue | undefined
  error: string | undefined
  disabled: boolean
  onChange: (value: ParamValue) => void
}

function ParamField({ spec, value, error, disabled, onChange }: FieldProps) {
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
      <select id={id} value={String(value)} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        {spec.options.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    )
  } else if (spec.kind === 'bool') {
    control = (
      <input id={id} type="checkbox" checked={value === true} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
    )
  } else {
    control = (
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
    )
  }
  return (
    <div className="field" title={spec.help || undefined}>
      <label htmlFor={id}>{spec.label}</label>
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
  onChange: (key: string, value: ParamValue) => void
  empty?: string
}

function Section({ title, scope, specs, values, errors, disabled, open, onChange, empty }: SectionProps) {
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
              error={errors[`${scope}.${spec.key}`] ?? (validateParam(spec, values[spec.key]) ?? undefined)}
              disabled={disabled}
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
  onChange: (scope: 'agent_params' | 'env_params' | 'training', key: string, value: ParamValue) => void
}

/** Parameter forms generated from the backend's declarative specs. */
export function ConfigPanel({ catalog, draft, errors, disabled, onChange }: Props) {
  const agent = findAgent(catalog, draft.agent)
  const env = findEnvironment(catalog, draft.environment)
  // Simulation speed is a live playback control (toolbar), not an initialization setting.
  const training = catalog.training_params.filter((spec) => spec.key !== 'simulation_speed')
  return (
    <div>
      {disabled && (
        <p className="note">Configuration is locked while a session is active. Reset or stop, then initialize again to apply changes.</p>
      )}
      <Section
        title={agent ? `${agent.name} hyperparameters` : 'Agent hyperparameters'}
        scope="agent_params"
        specs={agent?.params ?? []}
        values={draft.agent_params}
        errors={errors}
        disabled={disabled}
        open
        empty="Select an agent to configure it."
        onChange={(k, v) => onChange('agent_params', k, v)}
      />
      <Section
        title={env ? `${env.name} settings` : 'Environment settings'}
        scope="env_params"
        specs={env?.params ?? []}
        values={draft.env_params}
        errors={errors}
        disabled={disabled}
        open
        empty="Select an environment to configure it."
        onChange={(k, v) => onChange('env_params', k, v)}
      />
      <Section
        title="Training"
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
