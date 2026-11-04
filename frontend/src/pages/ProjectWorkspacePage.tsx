import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import { useActiveProject } from '../contexts/ActiveProjectContext'
import { ProjectIntentPanel } from '../features/projects/ProjectIntentPanel'
import { TRAINING_LABEL, configLabel, formatWhen } from '../features/projects/projectFormat'
import type { ProjectRun, ProjectSummary } from '../schemas/projects'
import type { ServiceError } from '../services/types'
import { createProjectService } from '../services/projects'
import type { ProjectService } from '../services/projects'
import '../features/projects/projects.css'

type State =
  | { state: 'loading' }
  | { state: 'error'; error: ServiceError }
  | { state: 'ready'; project: ProjectSummary }

const defaultService = createProjectService()

/**
 * The selected project's workspace. Opening it makes the project the active context for the rest of the
 * application (Studio training, monitoring, reports, diagnosis) and shows only this project's own runs.
 */
export function ProjectWorkspacePage({ service = defaultService }: { service?: ProjectService }) {
  const { projectId = '' } = useParams()
  const navigate = useNavigate()
  const { activeProjectId, setActiveProjectId } = useActiveProject()
  const [state, setState] = useState<State>({ state: 'loading' })
  const [runs, setRuns] = useState<ProjectRun[]>([])

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const [project, projectRuns] = await Promise.all([
        service.getProject(projectId, signal),
        service.listRuns(projectId, signal),
      ])
      if (signal?.aborted) return
      if (project.state === 'error') {
        if (project.error.kind !== 'cancelled') setState({ state: 'error', error: project.error })
        return
      }
      setState({ state: 'ready', project: project.data })
      if (projectRuns.state === 'ok') setRuns(projectRuns.data)
    },
    [projectId, service],
  )

  useEffect(() => {
    const controller = new AbortController()
    // Subscribing to the backend (an external system): state is set when the response arrives.
    setState({ state: 'loading' })
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  useEffect(() => {
    if (state.state === 'ready' && activeProjectId !== projectId) setActiveProjectId(projectId)
    if (
      state.state === 'error' &&
      state.error.kind === 'not_found' &&
      activeProjectId === projectId
    ) {
      setActiveProjectId(null)
    }
  }, [state, activeProjectId, projectId, setActiveProjectId])

  if (state.state === 'loading') {
    return (
      <ApplicationShell>
        <p role="status" aria-busy="true" className="pw-muted">
          Loading project…
        </p>
      </ApplicationShell>
    )
  }

  if (state.state === 'error') {
    return (
      <ApplicationShell>
        <div className="pw-card" role="alert">
          <h2>
            {state.error.kind === 'not_found'
              ? 'Project not found'
              : 'The project could not be loaded'}
          </h2>
          <p className="pw-card__lead">
            {state.error.kind === 'not_found'
              ? 'It may have been deleted, or the link is wrong.'
              : state.error.message}
          </p>
          <Link to="/projects" className="pw-button">
            Back to projects
          </Link>
        </div>
      </ApplicationShell>
    )
  }

  const { project } = state
  const agent = configLabel(project, 'agent')
  const environment = configLabel(project, 'environment')

  return (
    <ApplicationShell>
      <div className="pw">
        <header className="pw-head">
          <div>
            <p className="pw-eyebrow">Project</p>
            <h1 className="pw-title">{project.name}</h1>
            {project.description ? <p className="pw-sub">{project.description}</p> : null}
            <div className="pw-line" style={{ marginTop: 'var(--space-3)' }}>
              <span className="pw-badge pw-badge--strong">
                {TRAINING_LABEL[project.training.state]}
              </span>
              <span className={`pw-badge${agent ? '' : ' pw-badge--dashed'}`}>
                Agent: {agent ?? 'not configured'}
              </span>
              <span className={`pw-badge${environment ? '' : ' pw-badge--dashed'}`}>
                Environment: {environment ?? 'not configured'}
              </span>
              <span className="pw-muted">
                Created {formatWhen(project.created_at)} · modified {formatWhen(project.updated_at)}
              </span>
            </div>
          </div>
          <div className="pw-actions">
            <Link to="/projects" className="pw-button">
              All projects
            </Link>
            <button
              type="button"
              className="pw-button pw-button--solid"
              onClick={() => navigate('/studio?view=training')}
            >
              Open in Studio
            </button>
          </div>
        </header>

        <section className="pw-card" aria-label="Training runs">
          <h2>Training runs</h2>
          <p className="pw-card__lead">Only runs started from this project appear here.</p>
          {runs.length === 0 ? (
            <p className="pw-note">
              Training has not started. Configure an agent and environment in Studio and start a
              run; it will be recorded under this project.
            </p>
          ) : (
            <ul className="pw-list">
              {runs.map((run) => (
                <li key={run.run_id}>
                  <div className="pw-line">
                    <span className="pw-text pw-mono">{run.run_id}</span>
                    <span className="pw-badge pw-badge--strong">{run.status}</span>
                    {run.agent ? <span className="pw-badge">{run.agent}</span> : null}
                    {run.environment_id ? (
                      <span className="pw-badge">{run.environment_id}</span>
                    ) : null}
                  </div>
                  <span className="pw-muted">
                    {run.episode_count ?? 0} episodes · {run.step_count ?? 0} steps · started{' '}
                    {formatWhen(run.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <ProjectIntentPanel
          projectId={project.project_id}
          service={service}
          onChanged={() => void load()}
        />
      </div>
    </ApplicationShell>
  )
}
