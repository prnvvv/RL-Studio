/**
 * Draft configuration helpers: defaults from the catalog, client-side
 * validation mirroring the backend specs, and lifecycle control gating.
 *
 * Client validation is a convenience only; the backend re-validates everything.
 */
import {
  ACTIVE_STATUSES,
  type AgentTemplate,
  type Catalog,
  type EnvironmentTemplate,
  type ParamSpec,
  type ParamValue,
  type ParamValues,
  type SessionConfig,
  type SessionStatus,
} from './studioTypes'

export interface Draft {
  agent: string | null
  environment: string | null
  agent_params: ParamValues
  env_params: ParamValues
  training: ParamValues
}

export function defaultParams(specs: ParamSpec[]): ParamValues {
  return Object.fromEntries(specs.map((spec) => [spec.key, spec.default]))
}

export function emptyDraft(catalog: Catalog): Draft {
  return {
    agent: null,
    environment: null,
    agent_params: {},
    env_params: {},
    training: defaultParams(catalog.training_params),
  }
}

export function findAgent(catalog: Catalog, key: string | null): AgentTemplate | undefined {
  return catalog.agents.find((agent) => agent.key === key)
}

export function findEnvironment(
  catalog: Catalog,
  key: string | null,
): EnvironmentTemplate | undefined {
  return catalog.environments.find((env) => env.key === key)
}

export function isCompatible(catalog: Catalog, agent: string | null, environment: string | null) {
  if (agent === null || environment === null) return true
  return findEnvironment(catalog, environment)?.compatible_agents.includes(agent) ?? false
}

/** Why an agent/environment pairing cannot run, or null when it can. */
export function incompatibilityReason(
  catalog: Catalog,
  agent: string | null,
  environment: string | null,
): string | null {
  if (agent === null || environment === null || isCompatible(catalog, agent, environment)) {
    return null
  }
  const env = findEnvironment(catalog, environment)
  const template = findAgent(catalog, agent)
  if (!env || !template) return 'Unknown agent or environment.'
  return `${template.name} supports ${template.action_spaces.join('/')} actions; ${env.name} uses ${env.action_space.type} actions.`
}

/** Select an agent: reset only that agent's parameters; keep other sections. */
export function selectAgent(catalog: Catalog, draft: Draft, key: string): Draft {
  const agent = findAgent(catalog, key)
  if (!agent) return draft
  return { ...draft, agent: key, agent_params: defaultParams(agent.params) }
}

export function selectEnvironment(catalog: Catalog, draft: Draft, key: string): Draft {
  const env = findEnvironment(catalog, key)
  if (!env) return draft
  return { ...draft, environment: key, env_params: defaultParams(env.params) }
}

export function validateParam(spec: ParamSpec, value: ParamValue | undefined): string | null {
  if (value === undefined || value === '') return 'Required'
  if (spec.kind === 'bool') return typeof value === 'boolean' ? null : 'Must be on or off'
  if (spec.kind === 'choice') {
    return typeof value === 'string' && spec.options.includes(value) ? null : 'Pick an option'
  }
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'Must be a number'
  if (spec.kind === 'int' && !Number.isInteger(value)) return 'Must be a whole number'
  if (spec.min !== null && value < spec.min) return `Must be at least ${spec.min}`
  if (spec.max !== null && value > spec.max) return `Must be at most ${spec.max}`
  return null
}

export type FieldErrors = Record<string, string>

export function validateDraft(catalog: Catalog, draft: Draft): FieldErrors {
  const errors: FieldErrors = {}
  const agent = findAgent(catalog, draft.agent)
  const env = findEnvironment(catalog, draft.environment)
  const check = (scope: string, specs: ParamSpec[], values: ParamValues) => {
    for (const spec of specs) {
      const message = validateParam(spec, values[spec.key])
      if (message) errors[`${scope}.${spec.key}`] = message
    }
  }
  if (agent) check('agent_params', agent.params, draft.agent_params)
  if (env) check('env_params', env.params, draft.env_params)
  check('training', catalog.training_params, draft.training)

  if (agent?.key === 'PPO') {
    const batch = draft.agent_params.batch_size
    const steps = draft.agent_params.n_steps
    if (typeof batch === 'number' && typeof steps === 'number' && batch > steps) {
      errors['agent_params.batch_size'] = 'Must not exceed steps per update'
    }
  }
  if (agent?.key === 'DQN') {
    const starts = draft.agent_params.learning_starts
    const total = draft.training.total_timesteps
    if (typeof starts === 'number' && typeof total === 'number' && starts >= total) {
      errors['agent_params.learning_starts'] = 'Must be below total timesteps'
    }
  }
  return errors
}

/** The draft that reproduces a live session, so the panels show what is actually running. */
export function draftFromConfig(catalog: Catalog, config: SessionConfig): Draft {
  return {
    agent: config.agent,
    environment: config.environment,
    agent_params: { ...config.agent_params },
    env_params: { ...config.env_params },
    training: { ...defaultParams(catalog.training_params), ...config.training },
  }
}

export function toSessionConfig(draft: Draft): SessionConfig | null {
  if (draft.agent === null || draft.environment === null) return null
  return {
    agent: draft.agent,
    environment: draft.environment,
    agent_params: draft.agent_params,
    env_params: draft.env_params,
    training: draft.training,
  }
}

export interface ControlAvailability {
  initialize: boolean
  train: boolean
  pause: boolean
  resume: boolean
  stop: boolean
  reset: boolean
  /** Manual control can be taken or released. */
  manual: boolean
}

/**
 * Which controls are legal for a session status. Mirrors the backend state
 * machine so the UI never offers an action the backend would reject; the
 * backend remains authoritative.
 */
export function controlAvailability(
  status: SessionStatus | null,
  pendingCommand: 'pause' | null,
  canInitialize: boolean,
): ControlAvailability {
  const active = status !== null && ACTIVE_STATUSES.includes(status)
  return {
    initialize: canInitialize && !active,
    train: status === 'initialized',
    pause: status === 'running' && pendingCommand !== 'pause',
    resume: status === 'paused' || (status === 'running' && pendingCommand === 'pause'),
    stop: status === 'running' || status === 'paused',
    manual: status === 'running' || status === 'paused',
    reset:
      status === 'initialized' ||
      status === 'stopped' ||
      status === 'completed' ||
      status === 'failed',
  }
}

export const SPEED_OPTIONS: ReadonlyArray<{ label: string; value: number }> = [
  { label: '0.25×', value: 0.25 },
  { label: '0.5×', value: 0.5 },
  { label: '1×', value: 1 },
  { label: '2×', value: 2 },
  { label: '4×', value: 4 },
  { label: '8×', value: 8 },
  { label: '16×', value: 16 },
  { label: '32×', value: 32 },
  { label: 'Max', value: 0 },
]

/** The single control that deserves the eye right now, derived from the session state. */
export function primaryAction(
  status: SessionStatus | null,
  availability: ControlAvailability,
): 'initialize' | 'train' | 'pause' | 'resume' | null {
  if (availability.train) return 'train'
  if (status === 'paused' && availability.resume) return 'resume'
  if (availability.pause) return 'pause'
  if (availability.initialize) return 'initialize'
  return null
}

/** Human wording for each disturbance the backend can inject. */
export const CHAOS_KIND_LABELS: Record<string, { label: string; help: string }> = {
  impulse: {
    label: 'Sudden force',
    help: 'A sudden sideways velocity kick applied to the cart (a real change to the physics state).',
  },
  slip: {
    label: 'Actuator slip',
    help: 'Now and then the action actually executed is replaced by a random one.',
  },
  sensor_noise: {
    label: 'Sensor noise',
    help: 'Gaussian noise is added to what the agent observes. The environment itself is unchanged.',
  },
}
