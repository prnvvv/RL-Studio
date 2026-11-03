import { ParamSection } from './ConfigPanel'
import { findAgent } from './studioConfig'
import type { FieldErrors } from './studioConfig'
import type { Catalog, ParamValue, ParamValues } from './studioTypes'

interface Props {
  catalog: Catalog
  /** Environment both sides will play. Null until one is chosen. */
  environment: string | null
  agentB: string | null
  paramsB: ParamValues
  errors: FieldErrors
  disabled: boolean
  onSelectAgentB: (key: string) => void
  onChangeParamB: (key: string, value: ParamValue) => void
}

/** Setup for the opponent in Compare mode: same environment, seed and training budget as side A. */
export function CompareSetup({
  catalog,
  environment,
  agentB,
  paramsB,
  errors,
  disabled,
  onSelectAgentB,
  onChangeParamB,
}: Props) {
  const choices = catalog.agents.filter(
    (agent) => environment === null || agent.compatible_environments.includes(environment),
  )
  const selected = findAgent(catalog, agentB)
  return (
    <div className="compare-setup">
      <p className="note">
        Compare mode trains two agents on the same environment, environment settings, seed and
        training budget. Side A is the agent chosen on the first tab; choose side B here.
      </p>
      <div className="field">
        <span className="field__label">
          <label htmlFor="agent-b">Agent B</label>
        </span>
        <select
          id="agent-b"
          value={agentB ?? ''}
          disabled={disabled}
          onChange={(event) => onSelectAgentB(event.target.value)}
        >
          <option value="" disabled>
            Select an opponent
          </option>
          {choices.map((agent) => (
            <option key={agent.key} value={agent.key}>
              {agent.name}
            </option>
          ))}
        </select>
      </div>
      <ParamSection
        title={selected ? `${selected.name} (B) hyperparameters` : 'Agent B hyperparameters'}
        scope="agent_params"
        specs={selected?.params ?? []}
        values={paramsB}
        errors={errors}
        disabled={disabled}
        open
        empty={
          selected?.kind === 'custom'
            ? 'An uploaded model runs inference only and has no hyperparameters.'
            : 'Select an opponent to configure it.'
        }
        onChange={onChangeParamB}
      />
    </div>
  )
}
