import type { ParamSpec } from './studioTypes'

/**
 * Plain-language explanations shown in the `?` tooltips, keyed by parameter
 * key. They explain what a setting means; the limits and defaults shown next
 * to them always come from the backend's spec.
 */
export const PARAM_HELP: Record<string, string> = {
  learning_rate:
    'Step size of the optimizer. Too high and learning becomes unstable; too low and it crawls. Common values are 1e-4 to 1e-3.',
  gamma:
    'Discount factor: how much a future reward is worth compared with an immediate one. Closer to 1 favours long-term payoff.',
  n_steps:
    'Environment steps collected for each policy update before the agent trains on them. Larger batches are steadier but update less often.',
  batch_size:
    'Number of samples used in each gradient step. It must not exceed the steps collected per update.',
  n_epochs: 'How many passes the optimizer makes over each collected batch of experience.',
  ent_coef:
    'Entropy bonus weight. Higher values reward more random behaviour, which encourages exploration but can slow convergence.',
  clip_range:
    'PPO clip range: how far one update may move the policy from the previous one (the probability ratio is clipped to 1 ± this value). Smaller is safer but slower.',
  gae_lambda:
    'GAE lambda: smooths advantage estimates. Near 1 lowers bias but raises variance; lower values do the reverse.',
  vf_coef: 'Weight of the value-function loss relative to the policy loss.',
  buffer_size: 'Number of past transitions kept in the replay buffer for off-policy learning.',
  learning_starts: 'Steps of random experience collected before learning begins.',
  train_freq: 'Environment steps between gradient updates.',
  target_update_interval:
    'Steps between copying the online Q-network into the slower-moving target network.',
  exploration_fraction:
    'Share of training over which epsilon (random-action probability) is annealed down.',
  exploration_final_eps:
    'Epsilon once annealing finishes: the lasting chance of a random exploratory action.',
  net_arch:
    'Hidden layer sizes of the policy and value networks. Bigger networks can learn more but train slower.',
  total_timesteps:
    'Environment steps to run. For an uploaded model this is how many steps of inference to play.',
  seed: 'Seeds the algorithm and environment so a run can be reproduced exactly.',
  checkpoint_every: 'Timesteps between saved model checkpoints (0 turns checkpoints off).',
  eval_every:
    'Timesteps between deterministic evaluations on a separate environment (0 turns them off).',
  eval_episodes: 'Episodes played in each evaluation. More episodes give a steadier estimate.',
  device: 'Where the networks run. CUDA appears only when a GPU is available to the backend.',
  max_episode_steps: 'Steps before an episode is cut off (truncated) even if it has not ended.',
  gravity: 'Gravitational acceleration applied to the environment.',
  pole_length: 'Half the pole length. Longer poles fall more slowly and are easier to balance.',
  force_mag: 'Force applied to the cart by each push action.',
  wind_probability: 'Chance each step of a sideways velocity impulse (a disturbance).',
  wind_strength: 'Size of the velocity impulse the wind applies.',
  difficulty: 'Grid size and obstacle count for the generated warehouse.',
  layout_seed: 'Seeds obstacle placement so the same layout can be rebuilt.',
  goal_reward: 'Reward granted when the agent reaches the goal cell.',
  step_reward: 'Reward added on every step. A small negative value rewards finishing quickly.',
  collision_penalty: 'Penalty subtracted when the agent hits a wall or obstacle.',
  collision_ends_episode: 'When on, a collision ends the episode instead of only costing reward.',
}

function formatLimit(value: number): string {
  return Math.abs(value) >= 1000 || (Math.abs(value) > 0 && Math.abs(value) < 0.001)
    ? value.toExponential(0)
    : String(value)
}

/** Range and default for a parameter, taken from the backend spec. */
export function paramFacts(spec: ParamSpec): string {
  const parts: string[] = []
  if (spec.kind === 'int' || spec.kind === 'float') {
    if (spec.min !== null && spec.max !== null) {
      parts.push(`Range ${formatLimit(spec.min)} to ${formatLimit(spec.max)}`)
    }
  }
  if (spec.kind === 'choice' && spec.options.length > 0)
    parts.push(`Options: ${spec.options.join(', ')}`)
  parts.push(
    `Default ${typeof spec.default === 'number' ? formatLimit(spec.default) : String(spec.default)}`,
  )
  return parts.join(' · ')
}

/** Explanation shown for a parameter: the long-form copy when known, else the backend's one-liner. */
export function paramExplanation(spec: ParamSpec): string {
  return PARAM_HELP[spec.key] ?? (spec.help || spec.label)
}
