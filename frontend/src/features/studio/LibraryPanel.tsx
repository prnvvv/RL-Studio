import { useEffect, useState } from 'react'
import { MAX_LAYOUT_BYTES } from '../../services/studio'
import { useCarousel } from './useCarousel'
import { UploadDropzone, type UploadHooks, type UploadOutcome } from './UploadDropzone'
import { findAgent, findEnvironment, incompatibilityReason } from './studioConfig'
import type { Draft } from './studioConfig'
import {
  AgentGraph,
  AgentIcon,
  CheckBadge,
  CubeIcon,
  EnvironmentPreview,
  LayersIcon,
} from './libraryVisuals'
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

/** "Proximal Policy Optimization. Clipped ..." becomes "Proximal Policy Optimization". */
function fullName(agent: AgentTemplate): string {
  const first = agent.description.split(/\.\s|\.$/)[0]?.trim()
  return first && first.length <= 40 ? first : agent.name
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
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

function CarouselNav({
  label,
  edges,
  onPage,
}: {
  label: string
  edges: { start: boolean; end: boolean }
  onPage: (direction: 1 | -1) => void
}) {
  if (!edges.start && !edges.end) return null
  return (
    <div className="carousel-nav" role="group" aria-label={`Scroll ${label}`}>
      <button
        type="button"
        aria-label={`Previous ${label}`}
        disabled={!edges.start}
        onClick={() => onPage(-1)}
      >
        ‹
      </button>
      <button
        type="button"
        aria-label={`Next ${label}`}
        disabled={!edges.end}
        onClick={() => onPage(1)}
      >
        ›
      </button>
    </div>
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
  const agentRow = useCarousel(catalog.agents.length)
  const envRow = useCarousel(catalog.environments.length)
  const revealAgent = agentRow.reveal
  const revealEnv = envRow.reveal
  useEffect(revealAgent, [revealAgent, draft.agent])
  useEffect(revealEnv, [revealEnv, draft.environment])
  const selectedAgent = findAgent(catalog, draft.agent)
  const selectedEnv = findEnvironment(catalog, draft.environment)
  // Real compatibility metadata: the selected environment's built-in agents, otherwise every
  // built-in agent that at least one environment supports.
  const compatibleAgents = (
    selectedEnv
      ? selectedEnv.compatible_agents
      : [...new Set(catalog.environments.flatMap((env) => env.compatible_agents))]
  ).filter((key) => !key.startsWith('custom:'))

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

      <div className="section-head">
        <h3>
          <LayersIcon size={16} />
          <span>Agents</span>
          <span className="count-badge" aria-label={`${catalog.agents.length} agents`}>
            {catalog.agents.length}
          </span>
        </h3>
        <CarouselNav label="agents" edges={agentRow.edges} onPage={agentRow.page} />
      </div>
      <div
        className="carousel"
        data-start={agentRow.edges.start || undefined}
        data-end={agentRow.edges.end || undefined}
      >
        <div
          role="radiogroup"
          aria-label="Agent"
          className="carousel__track agent-grid"
          ref={agentRow.trackRef}
          onScroll={agentRow.update}
        >
          {catalog.agents.map((agent) => {
            const compatible =
              draft.environment === null ||
              agent.compatible_environments.includes(draft.environment)
            const custom = agent.kind === 'custom'
            const details = agentDetails(agent)
            const selected = draft.agent === agent.key
            return (
              <div key={agent.key} className="choice-wrap agent-wrap">
                <button
                  type="button"
                  role="radio"
                  className="agent-card"
                  data-selected={selected || undefined}
                  data-incompatible={!compatible || undefined}
                  aria-checked={selected}
                  disabled={locked}
                  onClick={() => onSelectAgent(agent.key)}
                >
                  <span className="agent-card__top">
                    <span className="agent-card__icon">
                      <AgentIcon agentKey={custom ? 'custom' : agent.key} />
                    </span>
                    <span className="agent-card__badge">{custom ? 'uploaded' : agent.family}</span>
                  </span>
                  <span className="agent-card__abbr">{agent.name}</span>
                  <span className="agent-card__name">
                    {custom ? agent.description : fullName(agent)}
                  </span>
                  {custom ? (
                    details && <span className="agent-card__details">{details}</span>
                  ) : (
                    <AgentGraph agentKey={agent.key} />
                  )}
                  <span className="agent-card__tags">
                    {agent.action_spaces.map((space) => (
                      <span key={space} className="tag">
                        {capitalize(space)}
                      </span>
                    ))}
                    {!compatible && (
                      <span className="tag tag--off">not compatible with selection</span>
                    )}
                  </span>
                  {custom && <span className="agent-card__reserve" aria-hidden="true" />}
                </button>
                {selected && <CheckBadge />}
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
      </div>
      <UploadDropzone
        label="Drag & drop a custom model"
        accept={MODEL_EXTENSIONS}
        hint="Stable-Baselines3 .zip or .pt state dict. Pickle and ONNX files are not accepted."
        maxBytes={catalog.limits?.max_model_bytes ?? FALLBACK_MODEL_LIMIT}
        disabled={locked}
        upload={uploadModel}
      />

      <div className="section-head">
        <h3>
          <CubeIcon size={16} />
          <span>Environments</span>
          <span className="count-badge" aria-label={`${catalog.environments.length} environments`}>
            {catalog.environments.length}
          </span>
        </h3>
        {compatibleAgents.length > 0 && (
          <div className="compat" aria-label="Compatible agents">
            <span>Compatible with</span>
            {compatibleAgents.map((key) => (
              <span key={key} className="tag">
                {findAgent(catalog, key)?.name ?? key}
              </span>
            ))}
          </div>
        )}
        <CarouselNav label="environments" edges={envRow.edges} onPage={envRow.page} />
      </div>
      <div
        className="carousel"
        data-start={envRow.edges.start || undefined}
        data-end={envRow.edges.end || undefined}
      >
        <div
          role="radiogroup"
          aria-label="Environment"
          className="carousel__track env-list"
          ref={envRow.trackRef}
          onScroll={envRow.update}
        >
          {catalog.environments.map((env) => {
            const compatible = draft.agent === null || env.compatible_agents.includes(draft.agent)
            const custom = env.kind === 'custom'
            const details = envDetails(env)
            const selected = draft.environment === env.key
            const unavailable = env.available === false
            return (
              <div key={env.key} className="choice-wrap env-wrap">
                <button
                  type="button"
                  role="radio"
                  className="env-card"
                  data-selected={selected || undefined}
                  data-incompatible={!compatible || undefined}
                  data-unavailable={unavailable || undefined}
                  aria-checked={selected}
                  disabled={locked || unavailable}
                  title={unavailable ? (env.unavailable_reason ?? 'Not available here') : undefined}
                  onClick={() => onSelectEnvironment(env.key)}
                >
                  <span className="env-card__preview">
                    <EnvironmentPreview
                      envKey={env.key}
                      renderer={env.renderer}
                      layout={env.custom?.layout}
                    />
                  </span>
                  <span className="env-card__body">
                    <span className="env-card__title">{env.name}</span>
                    <span className="env-card__desc">{env.description}</span>
                    {details && <span className="env-card__meta">{details}</span>}
                    {unavailable && (
                      <span className="env-card__meta env-card__meta--warn">
                        Unavailable: {env.unavailable_reason}
                      </span>
                    )}
                    <span className="env-card__meta">
                      obs {spaceLabel(env.observation_space)} · act {spaceLabel(env.action_space)}
                    </span>
                    <span className="env-card__tags">
                      <span className="tag">{custom ? 'uploaded grid' : env.dimension}</span>
                      {!custom && <span className="tag">{capitalize(env.difficulty)}</span>}
                      <span className="tag">{capitalize(env.action_space.type)}</span>
                      {env.compatible_agents
                        .filter((key) => !key.startsWith('custom:'))
                        .map((agent) => (
                          <span key={agent} className="tag">
                            {findAgent(catalog, agent)?.name ?? agent}
                          </span>
                        ))}
                      {!compatible && (
                        <span className="tag tag--off">not compatible with selection</span>
                      )}
                    </span>
                  </span>
                </button>
                {selected && <CheckBadge />}
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
