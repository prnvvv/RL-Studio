import { incompatibilityReason } from './studioConfig'
import type { Draft } from './studioConfig'
import type { Catalog, SpaceDescription } from './studioTypes'

interface Props {
  catalog: Catalog
  draft: Draft
  /** When true a session is active; selections are frozen so it is never replaced silently. */
  locked: boolean
  onSelectAgent: (key: string) => void
  onSelectEnvironment: (key: string) => void
}

function spaceLabel(space: SpaceDescription): string {
  if (space.type === 'discrete') return `Discrete(${space.n})`
  if (space.type === 'box') return `Box(${(space.shape ?? []).join('×')})`
  return space.type
}

/** Agent and environment templates, straight from the backend catalog. */
export function LibraryPanel({
  catalog,
  draft,
  locked,
  onSelectAgent,
  onSelectEnvironment,
}: Props) {
  const reason = incompatibilityReason(catalog, draft.agent, draft.environment)
  return (
    <div>
      {locked && (
        <p className="note" role="status">
          A session is active. Stop it to change the agent or environment — the running session is
          never replaced silently.
        </p>
      )}

      <h3 className="section-title">Agents</h3>
      <div role="radiogroup" aria-label="Agent">
        {catalog.agents.map((agent) => {
          const compatible =
            draft.environment === null || agent.compatible_environments.includes(draft.environment)
          return (
            <button
              key={agent.key}
              type="button"
              role="radio"
              className="choice"
              aria-checked={draft.agent === agent.key}
              disabled={locked}
              onClick={() => onSelectAgent(agent.key)}
            >
              <span className="choice__head">
                <span>{agent.name}</span>
                <span className="chip">{agent.family}</span>
              </span>
              <p>{agent.description}</p>
              <span className="chips">
                {agent.action_spaces.map((space) => (
                  <span key={space} className="chip">
                    {space} actions
                  </span>
                ))}
                {!compatible && (
                  <span className="chip chip--off">not compatible with selection</span>
                )}
              </span>
            </button>
          )
        })}
      </div>

      <h3 className="section-title">Environments</h3>
      <div role="radiogroup" aria-label="Environment">
        {catalog.environments.map((env) => {
          const compatible = draft.agent === null || env.compatible_agents.includes(draft.agent)
          return (
            <button
              key={env.key}
              type="button"
              role="radio"
              className="choice"
              aria-checked={draft.environment === env.key}
              disabled={locked}
              onClick={() => onSelectEnvironment(env.key)}
            >
              <span className="choice__head">
                <span>{env.name}</span>
                <span className="chip">
                  {env.dimension} · {env.difficulty}
                </span>
              </span>
              <p>{env.description}</p>
              <span className="chips">
                <span className="chip">obs {spaceLabel(env.observation_space)}</span>
                <span className="chip">act {spaceLabel(env.action_space)}</span>
                {env.compatible_agents.map((agent) => (
                  <span key={agent} className="chip">
                    {agent}
                  </span>
                ))}
                {!compatible && (
                  <span className="chip chip--off">not compatible with selection</span>
                )}
              </span>
            </button>
          )
        })}
      </div>

      {reason && (
        <p className="note note--error" role="alert">
          Incompatible pairing. {reason}
        </p>
      )}
      <p className="note">
        Only algorithms and environments the backend can actually run are listed. Compatibility is
        derived from each environment&apos;s real action space.
      </p>
    </div>
  )
}
