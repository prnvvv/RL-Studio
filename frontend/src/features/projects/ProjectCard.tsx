import { useState } from 'react'
import type { FormEvent } from 'react'
import type { ProjectSummary } from '../../schemas/projects'
import { TRAINING_LABEL, configLabel, formatWhen } from './projectFormat'

interface ProjectCardProps {
  project: ProjectSummary
  onOpen: (project: ProjectSummary) => void
  onRename: (project: ProjectSummary, name: string) => Promise<string | null>
  onDelete: (project: ProjectSummary) => void
}

export function ProjectCard({ project, onOpen, onRename, onDelete }: ProjectCardProps) {
  const [renaming, setRenaming] = useState(false)
  const [draft, setDraft] = useState(project.name)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const agent = configLabel(project, 'agent')
  const environment = configLabel(project, 'environment')
  const { training, requirements, last_verification: last } = project

  async function submit(event: FormEvent) {
    event.preventDefault()
    const next = draft.trim()
    if (next === '') {
      setError('Enter a name.')
      return
    }
    if (next === project.name) {
      setRenaming(false)
      return
    }
    setPending(true)
    const failure = await onRename(project, next)
    setPending(false)
    if (failure) setError(failure)
    else {
      setError(null)
      setRenaming(false)
    }
  }

  return (
    <article className="pj-card" aria-label={`Project ${project.name}`}>
      <div className="pj-card__top">
        {renaming ? (
          <form
            onSubmit={(e) => void submit(e)}
            style={{ display: 'flex', gap: 8, flex: 1, minWidth: 0 }}
          >
            <input
              className="pj-input"
              aria-label="Project name"
              value={draft}
              maxLength={120}
              onChange={(e) => setDraft(e.target.value)}
              disabled={pending}
              autoFocus
            />
            <button type="submit" className="pj-btn pj-btn--solid" disabled={pending}>
              Save
            </button>
            <button
              type="button"
              className="pj-btn"
              disabled={pending}
              onClick={() => {
                setRenaming(false)
                setDraft(project.name)
                setError(null)
              }}
            >
              Cancel
            </button>
          </form>
        ) : (
          <h2 className="pj-card__name">{project.name}</h2>
        )}
        <span className="pj-chip pj-chip--state">{TRAINING_LABEL[training.state]}</span>
      </div>
      {error ? (
        <p className="pj-error" role="alert">
          {error}
        </p>
      ) : null}
      {project.description ? <p className="pj-card__desc">{project.description}</p> : null}
      <div className="pj-chips">
        <span className={`pj-chip${agent ? '' : ' pj-chip--pending'}`}>
          Agent: {agent ?? 'not configured'}
        </span>
        <span className={`pj-chip${environment ? '' : ' pj-chip--pending'}`}>
          Environment: {environment ?? 'not configured'}
        </span>
      </div>
      <dl className="pj-meta">
        <div>
          <dt>Runs</dt>
          <dd>
            {training.run_count}
            {training.active_runs > 0 ? ` (${training.active_runs} active)` : ''}
          </dd>
        </div>
        <div>
          <dt>Requirements</dt>
          <dd>
            {requirements.confirmed} confirmed
            {requirements.pending > 0 ? `, ${requirements.pending} pending` : ''}
          </dd>
        </div>
        <div>
          <dt>Created</dt>
          <dd>{formatWhen(project.created_at)}</dd>
        </div>
        <div>
          <dt>Last modified</dt>
          <dd>{formatWhen(project.updated_at)}</dd>
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <dt>Last verification</dt>
          <dd>{last ? `${last.status.toUpperCase()} on ${last.run_id}` : 'None yet'}</dd>
        </div>
      </dl>
      <div className="pj-card__foot">
        <button type="button" className="pj-btn pj-btn--solid" onClick={() => onOpen(project)}>
          Open project
        </button>
        <button
          type="button"
          className="pj-btn"
          onClick={() => setRenaming(true)}
          disabled={renaming}
        >
          Rename
        </button>
        <button type="button" className="pj-btn pj-btn--danger" onClick={() => onDelete(project)}>
          Delete
        </button>
      </div>
    </article>
  )
}
