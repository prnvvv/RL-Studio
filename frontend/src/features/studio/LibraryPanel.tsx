import { useState } from 'react'
import { MAX_LAYOUT_BYTES } from '../../services/studio'
import { UploadDropzone, type UploadHooks, type UploadOutcome } from './UploadDropzone'
import { findAgent, findEnvironment, incompatibilityReason } from './studioConfig'
import type { Draft } from './studioConfig'
import type { AgentTemplate, Catalog, EnvironmentTemplate, SpaceDescription } from './studioTypes'

export type RemoveTarget = { kind: 'model' | 'environment'; id: string; key: string; name: string }

interface Props {
  catalog: Catalog
  draft: Draft
  /** When true a session is active; selections are frozen so it is never replaced silently. */
  locked: boolean
  onSelectAgent: (key: string) => void
  onSelectEnvironment: (key: string) => void
  /** Jump to the Configure tab. */
  onConfigure: () => void
  uploadModel: (file: File, hooks: UploadHooks) => Promise<UploadOutcome>
  uploadEnvironment: (file: File, hooks: UploadHooks) => Promise<UploadOutcome>
  onRemove: (target: RemoveTarget) => Promise<void>
}

const MODEL_EXTENSIONS = ['.zip', '.pt']
const FALLBACK_MODEL_LIMIT = 50 * 1024 * 1024

const LAYOUT_EXAMPLE = `{
  "name": "My grid",
  "rows": 4,
  "cols": 5,
  "start": [0, 0],
  "goal": [3, 4],
  "obstacles": [[1, 1], [2, 3]]
}`

function spaceLabel(space: SpaceDescription): string {
  if (space.type === 'discrete') return `Discrete(${space.n})`
  if (space.type === 'box') return `Box(${(space.shape ?? []).join('×')})`
  return space.type
}

function sizeLabel(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

function agentDetails(agent: AgentTemplate): string | null {
  const info = agent.custom
  if (!info) return null
  const algorithm = `${info.algorithm}${info.algorithm_inferred ? ' (inferred)' : ''}`
  return `${algorithm} · ${info.obs_dim} inputs → ${info.action_dim} ${info.action_type} · ${info.format} · ${sizeLabel(info.size_bytes)}`
}

function envDetails(env: EnvironmentTemplate): string | null {
  const layout = env.custom?.layout
  return layout ? `${layout.rows}×${layout.cols} grid · ${layout.obstacles.length} obstacles` : null
}

function RemoveButton({
  confirming,
  disabled,
  onClick,
  label,
}: {
  confirming: boolean
  disabled: boolean
  onClick: () => void
  label: string
}) {
  return (
    <button
      type="button"
      className="choice__remove"
      disabled={disabled}
      aria-label={`${confirming ? 'Confirm removing' : 'Remove'} ${label}`}
      onClick={onClick}
    >
      {confirming ? 'Confirm remove' : 'Remove'}
    </button>
  )
}

/** Agent and environment templates, straight from the backend catalog, plus custom uploads. */
export function LibraryPanel({
  catalog,
  draft,
  locked,
  onSelectAgent,
  onSelectEnvironment,
  onConfigure,
  uploadModel,
  uploadEnvironment,
  onRemove,
}: Props) {
  const reason = incompatibilityReason(catalog, draft.agent, draft.environment)
  const [confirming, setConfirming] = useState<string | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)
  const selectedAgent = findAgent(catalog, draft.agent)
  const selectedEnv = findEnvironment(catalog, draft.environment)

  async function remove(target: RemoveTarget) {
    if (confirming !== target.key) {
      setConfirming(target.key)
      return
    }
    setRemoving(target.key)
    await onRemove(target)
    setRemoving(null)
    setConfirming(null)
  }

  return (
    <div>
      {(selectedAgent || selectedEnv) && (
        <div className="configure-cta">
          <span>
            {selectedAgent?.name ?? 'No agent'} · {selectedEnv?.name ?? 'No environment'}
          </span>
          <button type="button" className="btn" onClick={onConfigure}>
            Configure →
          </button>
        </div>
      )}
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
          const custom = agent.kind === 'custom'
          const details = agentDetails(agent)
          return (
            <div key={agent.key} className="choice-wrap">
              <button
                type="button"
                role="radio"
                className="choice"
                aria-checked={draft.agent === agent.key}
                disabled={locked}
                onClick={() => onSelectAgent(agent.key)}
              >
                <span className="choice__head">
                  <span>{agent.name}</span>
                  <span className="chip">{custom ? 'uploaded' : agent.family}</span>
                </span>
                <p>{agent.description}</p>
                {details && <span className="choice__meta">{details}</span>}
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
                {custom && <span style={{ display: 'block', height: 22 }} aria-hidden="true" />}
              </button>
              {custom && agent.custom && (
                <RemoveButton
                  confirming={confirming === agent.key}
                  disabled={locked || removing === agent.key}
                  label={agent.name}
                  onClick={() =>
                    void remove({
                      kind: 'model',
                      id: agent.custom!.model_id,
                      key: agent.key,
                      name: agent.name,
                    })
                  }
                />
              )}
            </div>
          )
        })}
      </div>
      <UploadDropzone
        label="Drag & drop a custom model"
        accept={MODEL_EXTENSIONS}
        hint="Stable-Baselines3 .zip or .pt state dict. Pickle and ONNX files are not accepted."
        maxBytes={catalog.limits?.max_model_bytes ?? FALLBACK_MODEL_LIMIT}
        disabled={locked}
        upload={uploadModel}
      />

      <h3 className="section-title">Environments</h3>
      <div role="radiogroup" aria-label="Environment">
        {catalog.environments.map((env) => {
          const compatible = draft.agent === null || env.compatible_agents.includes(draft.agent)
          const custom = env.kind === 'custom'
          const details = envDetails(env)
          return (
            <div key={env.key} className="choice-wrap">
              <button
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
                    {custom ? 'uploaded grid' : `${env.dimension} · ${env.difficulty}`}
                  </span>
                </span>
                <p>{env.description}</p>
                {details && <span className="choice__meta">{details}</span>}
                <span className="chips">
                  <span className="chip">obs {spaceLabel(env.observation_space)}</span>
                  <span className="chip">act {spaceLabel(env.action_space)}</span>
                  {env.compatible_agents
                    .filter((key) => !key.startsWith('custom:'))
                    .map((agent) => (
                      <span key={agent} className="chip">
                        {agent}
                      </span>
                    ))}
                  {!compatible && (
                    <span className="chip chip--off">not compatible with selection</span>
                  )}
                </span>
                {custom && <span style={{ display: 'block', height: 22 }} aria-hidden="true" />}
              </button>
              {custom && env.custom && (
                <RemoveButton
                  confirming={confirming === env.key}
                  disabled={locked || removing === env.key}
                  label={env.name}
                  onClick={() =>
                    void remove({
                      kind: 'environment',
                      id: env.custom!.env_id,
                      key: env.key,
                      name: env.name,
                    })
                  }
                />
              )}
            </div>
          )
        })}
      </div>
      <UploadDropzone
        label="Drag & drop a custom grid environment"
        accept={['.json']}
        hint="A declarative warehouse grid (JSON). No code is executed."
        maxBytes={MAX_LAYOUT_BYTES}
        disabled={locked}
        upload={uploadEnvironment}
        example={{ summary: 'Layout format', text: LAYOUT_EXAMPLE }}
      />

      {reason && (
        <p className="note note--error" role="alert">
          Incompatible pairing. {reason}
        </p>
      )}
      <p className="note">
        Only algorithms and environments the backend can actually run are listed. Compatibility is
        derived from each environment&apos;s real observation and action spaces.
      </p>
    </div>
  )
}
