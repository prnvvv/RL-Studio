import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { TopNavigation } from '../components/layout/TopNavigation'
import { useActiveProject } from '../contexts/ActiveProjectContext'
import { LandingBackdrop } from '../features/landing/LandingBackdrop'
import { CreateProjectDialog } from '../features/projects/CreateProjectDialog'
import { DeleteProjectDialog } from '../features/projects/DeleteProjectDialog'
import { ProjectCard } from '../features/projects/ProjectCard'
import type { ProjectSummary } from '../schemas/projects'
import { createProjectService } from '../services/projects'
import type { ProjectService } from '../services/projects'
import '../features/landing/landing.css'
import '../features/projects/projects.css'

type ListState =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; projects: ProjectSummary[] }

const defaultService = createProjectService()

/**
 * Project Dashboard: the layer between the landing page and the Studio workspace. It renders the landing page's
 * own background component, so it reads as a continuation of it.
 */
export function ProjectsPage({ service = defaultService }: { service?: ProjectService }) {
  const navigate = useNavigate()
  const { setActiveProjectId } = useActiveProject()
  const [list, setList] = useState<ListState>({ state: 'loading' })
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null)
  const [deletePending, setDeletePending] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setList({ state: 'loading' })
      const result = await service.listProjects(signal)
      if (signal?.aborted) return
      if (result.state === 'ok') setList({ state: 'ready', projects: result.data })
      else if (result.error.kind !== 'cancelled')
        setList({ state: 'error', message: result.error.message })
    },
    [service],
  )

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  const open = useCallback(
    (project: ProjectSummary) => {
      setActiveProjectId(project.project_id)
      navigate(`/projects/${project.project_id}`)
    },
    [navigate, setActiveProjectId],
  )

  async function rename(project: ProjectSummary, name: string): Promise<string | null> {
    const result = await service.updateProject(project.project_id, { name })
    if (result.state === 'error') return `The project was not renamed. ${result.error.message}`
    setList((current) =>
      current.state === 'ready'
        ? {
            state: 'ready',
            projects: current.projects.map((p) =>
              p.project_id === project.project_id ? result.data : p,
            ),
          }
        : current,
    )
    return null
  }

  async function confirmDelete(confirmName: string) {
    if (!deleting) return
    setDeletePending(true)
    setDeleteError(null)
    const result = await service.deleteProject(deleting.project_id, confirmName)
    setDeletePending(false)
    if (result.state === 'error') {
      setDeleteError(
        result.error.kind === 'conflict'
          ? 'The project could not be deleted: stop its active training run first, and type the exact name.'
          : `The project was not deleted. ${result.error.message}`,
      )
      return
    }
    setActiveProjectId(null)
    setDeleting(null)
    void load()
  }

  return (
    <div className="ls-root pj-root">
      <LandingBackdrop className="pj-backdrop" />
      <div className="pj-page">
        <TopNavigation />
        <main className="pj-main">
          <header className="pj-head">
            <div>
              <p className="pj-eyebrow">Projects</p>
              <h1 className="pj-title">Your projects</h1>
              <p className="pj-sub">
                A project holds an agent, an environment, its expectations and every training run.
                Open one to continue, or start a new one.
              </p>
            </div>
            <div className="pj-actions">
              <button
                type="button"
                className="pj-btn pj-btn--solid"
                onClick={() => setCreating(true)}
              >
                Create project
              </button>
            </div>
          </header>

          {list.state === 'loading' ? (
            <div className="pj-state" role="status" aria-busy="true">
              <h2>Loading projects…</h2>
            </div>
          ) : list.state === 'error' ? (
            <div className="pj-state" role="alert">
              <h2>Projects could not be loaded</h2>
              <p>{list.message}</p>
              <button type="button" className="pj-btn" onClick={() => void load()}>
                Try again
              </button>
            </div>
          ) : list.projects.length === 0 ? (
            <div className="pj-state">
              <h2>No projects yet</h2>
              <p>
                Create a project to begin. You can describe what the agent should achieve first and
                configure the agent and environment later.
              </p>
              <button
                type="button"
                className="pj-btn pj-btn--solid"
                onClick={() => setCreating(true)}
              >
                Create your first project
              </button>
            </div>
          ) : (
            <section className="pj-grid" aria-label="Projects">
              {list.projects.map((project) => (
                <ProjectCard
                  key={project.project_id}
                  project={project}
                  onOpen={open}
                  onRename={rename}
                  onDelete={(p) => {
                    setDeleteError(null)
                    setDeleting(p)
                  }}
                />
              ))}
            </section>
          )}
        </main>
      </div>

      {creating ? (
        <CreateProjectDialog
          service={service}
          onCancel={() => setCreating(false)}
          onCreated={(project) => {
            setCreating(false)
            open(project)
          }}
        />
      ) : null}
      {deleting ? (
        <DeleteProjectDialog
          project={deleting}
          pending={deletePending}
          error={deleteError}
          onConfirm={(name) => void confirmDelete(name)}
          onCancel={() => setDeleting(null)}
        />
      ) : null}
    </div>
  )
}
