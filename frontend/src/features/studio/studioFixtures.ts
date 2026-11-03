import type { AgentTemplate, Catalog, EnvironmentTemplate, ParamSpec } from './studioTypes'

/** Small catalog used by component tests. Shapes mirror the backend catalog response. */
const spec = (
  key: string,
  label: string,
  kind: ParamSpec['kind'],
  def: ParamSpec['default'],
  min: number | null = null,
  max: number | null = null,
): ParamSpec => ({
  key,
  label,
  kind,
  default: def,
  help: `${label} help`,
  min,
  max,
  step: null,
  options: kind === 'choice' ? ['cpu'] : [],
})

export const TRAINING_SPECS: ParamSpec[] = [
  spec('total_timesteps', 'Total timesteps', 'int', 20000, 1000, 1000000),
  spec('seed', 'Training seed', 'int', 0, 0, 2147483647),
  spec('simulation_speed', 'Simulation speed', 'float', 4, 0, 64),
  spec('checkpoint_every', 'Checkpoint every', 'int', 5000, 0, 1000000),
  spec('eval_every', 'Evaluate every', 'int', 5000, 0, 1000000),
  spec('eval_episodes', 'Evaluation episodes', 'int', 5, 1, 50),
  spec('device', 'Device', 'choice', 'cpu'),
]

export const PPO: AgentTemplate = {
  key: 'PPO',
  kind: 'builtin',
  name: 'PPO',
  description: 'Proximal Policy Optimization.',
  family: 'on-policy',
  action_spaces: ['discrete', 'box'],
  params: [
    spec('learning_rate', 'Learning rate', 'float', 0.0003, 1e-6, 0.1),
    spec('gamma', 'Gamma', 'float', 0.99, 0.8, 0.9999),
    spec('clip_range', 'Clip range', 'float', 0.2, 0.05, 0.5),
    spec('gae_lambda', 'GAE lambda', 'float', 0.95, 0.8, 1),
  ],
  reported_metrics: ['policy_loss'],
  compatible_environments: ['cartpole'],
}

export const UPLOADED: AgentTemplate = {
  key: 'custom:mdl_abcdef123456',
  kind: 'custom',
  name: 'My policy',
  description: 'Uploaded zip policy (PPO). Runs inference only; it does not learn.',
  family: 'custom',
  action_spaces: ['discrete'],
  params: [],
  reported_metrics: [],
  compatible_environments: ['cartpole'],
  custom: {
    model_id: 'mdl_abcdef123456',
    name: 'My policy',
    original_filename: 'policy.zip',
    format: 'zip',
    sha256: 'a'.repeat(64),
    size_bytes: 45000,
    uploaded_at: '2026-01-01T00:00:00Z',
    algorithm: 'PPO',
    algorithm_inferred: true,
    obs_dim: 4,
    action_type: 'discrete',
    action_dim: 2,
    net_arch: { pi: [64, 64], vf: [64, 64] },
    activation: 'Tanh',
    activation_assumed: true,
  },
}

export const CARTPOLE: EnvironmentTemplate = {
  key: 'cartpole',
  kind: 'builtin',
  name: 'CartPole Balancing',
  description: 'Balance a pole on a cart.',
  dimension: '3D',
  difficulty: 'Beginner',
  renderer: 'cartpole',
  observation_space: { type: 'box', shape: [4] },
  action_space: { type: 'discrete', n: 2 },
  default_scene: { x_limit: 2.4, theta_limit: 0.2, pole_length: 1 },
  supports_disturbances: true,
  params: [spec('gravity', 'Gravity', 'float', 9.8, 1, 20)],
  compatible_agents: ['PPO', 'custom:mdl_abcdef123456'],
}

export const CATALOG: Catalog = {
  schema_version: '1.1',
  limits: { model_extensions: ['.zip', '.pt'], max_model_bytes: 50 * 1024 * 1024, max_grid: 20 },
  agents: [PPO, UPLOADED],
  environments: [CARTPOLE],
  training_params: TRAINING_SPECS,
  net_arches: ['medium (64x64)'],
}
