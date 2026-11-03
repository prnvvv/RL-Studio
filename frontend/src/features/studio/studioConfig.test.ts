import { describe, expect, it } from 'vitest'
import {
  controlAvailability,
  defaultParams,
  emptyDraft,
  incompatibilityReason,
  selectAgent,
  validateDraft,
  validateParam,
} from './studioConfig'
import type { Catalog, ParamSpec } from './studioTypes'

const intSpec: ParamSpec = {
  key: 'n_steps',
  label: 'Steps',
  kind: 'int',
  default: 512,
  help: '',
  min: 16,
  max: 8192,
  step: 16,
  options: [],
}

const catalog: Catalog = {
  schema_version: '1.0',
  net_arches: [],
  training_params: [{ ...intSpec, key: 'total_timesteps', default: 20000, min: 1000, max: 1_000_000 }],
  agents: [
    {
      key: 'PPO',
      name: 'PPO',
      description: '',
      family: 'on-policy',
      action_spaces: ['discrete', 'box'],
      params: [intSpec, { ...intSpec, key: 'batch_size', default: 64, min: 8 }],
      reported_metrics: [],
      compatible_environments: ['cartpole'],
    },
    {
      key: 'DQN',
      name: 'DQN',
      description: '',
      family: 'off-policy',
      action_spaces: ['discrete'],
      params: [],
      reported_metrics: [],
      compatible_environments: ['cartpole'],
    },
  ],
  environments: [
    {
      key: 'cartpole',
      name: 'CartPole',
      description: '',
      dimension: '3D',
      difficulty: 'Beginner',
      renderer: 'cartpole',
      observation_space: { type: 'box' },
      action_space: { type: 'discrete', n: 2 },
      default_scene: {},
      supports_disturbances: true,
      params: [],
      compatible_agents: ['PPO', 'DQN'],
    },
    {
      key: 'arm',
      name: 'Arm',
      description: '',
      dimension: '3D',
      difficulty: 'Advanced',
      renderer: 'arm',
      observation_space: { type: 'box' },
      action_space: { type: 'box' },
      default_scene: {},
      supports_disturbances: false,
      params: [],
      compatible_agents: ['PPO'],
    },
  ],
}

describe('param validation', () => {
  it('enforces bounds and integer-ness', () => {
    expect(validateParam(intSpec, 512)).toBeNull()
    expect(validateParam(intSpec, 8)).toMatch(/at least 16/)
    expect(validateParam(intSpec, 99999)).toMatch(/at most 8192/)
    expect(validateParam(intSpec, 20.5)).toMatch(/whole number/)
    expect(validateParam(intSpec, Number.NaN)).toMatch(/number/)
    expect(validateParam(intSpec, '')).toBe('Required')
  })

  it('applies cross-field rules for PPO', () => {
    let draft = selectAgent(catalog, emptyDraft(catalog), 'PPO')
    expect(validateDraft(catalog, draft)).toEqual({})
    draft = { ...draft, agent_params: { ...draft.agent_params, batch_size: 1024, n_steps: 64 } }
    expect(validateDraft(catalog, draft)['agent_params.batch_size']).toMatch(/exceed/)
  })
})

describe('compatibility', () => {
  it('explains an incompatible pairing from action spaces', () => {
    expect(incompatibilityReason(catalog, 'PPO', 'cartpole')).toBeNull()
    expect(incompatibilityReason(catalog, 'DQN', 'arm')).toMatch(/discrete.*box/)
  })

  it('switching agent resets only that agent parameters', () => {
    const draft = { ...emptyDraft(catalog), environment: 'cartpole', env_params: { x: 1 } }
    const next = selectAgent(catalog, draft, 'PPO')
    expect(next.env_params).toEqual({ x: 1 })
    expect(next.agent_params).toEqual(defaultParams(catalog.agents[0].params))
  })
})

describe('control availability', () => {
  it('mirrors the backend state machine', () => {
    expect(controlAvailability('initialized', null, true)).toMatchObject({
      train: true,
      pause: false,
      stop: false,
      reset: true,
      initialize: true,
    })
    expect(controlAvailability('running', null, true)).toMatchObject({
      pause: true,
      stop: true,
      reset: false,
      initialize: false,
    })
    expect(controlAvailability('running', 'pause', true)).toMatchObject({
      pause: false,
      resume: true,
    })
    expect(controlAvailability('paused', null, true).resume).toBe(true)
    expect(controlAvailability('stopping', null, true)).toMatchObject({
      stop: false,
      reset: false,
      initialize: false,
    })
    expect(controlAvailability('completed', null, true)).toMatchObject({ reset: true, train: false })
    expect(controlAvailability(null, null, false).initialize).toBe(false)
  })
})
