import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useActiveProject } from '../../contexts/ActiveProjectContext'
import { createProjectService } from '../../services/projects'
import type { ProjectService } from '../../services/projects'
import '../projects/projects.css'

const defaultService = createProjectService()

/**
 * Shows which project the workspace is operating in, on every page that renders the shared navigation. It renders
 * nothing when no project is active. A project that no longer exists is dropped rather than shown as active.
 */
export function ActiveProjectChip({ service = defaultService }: { service?: ProjectService }) {
  const { activeProjectId, setActiveProjectId } = useActiveProject()
  const [loaded, setLoaded] = useState<{ id: string; name: string | null } | null>(null)

  useEffect(() => {
    if (activeProjectId === null) return
    const controller = new AbortController()
    void service.getProject(activeProjectId, controller.signal).then((result) => {
      if (controller.signal.aborted) return
      if (result.state === 'ok') setLoaded({ id: activeProjectId, name: result.data.name })
      else if (result.error.kind === 'not_found') setActiveProjectId(null)
      else setLoaded({ id: activeProjectId, name: null }) // unreachable backend: keep the pointer, name unknown
    })
    return () => controller.abort()
  }, [activeProjectId, service, setActiveProjectId])

  if (activeProjectId === null) return null
  const name = loaded?.id === activeProjectId ? loaded.name : null
  return (
    <Link
      to={`/projects/${activeProjectId}`}
      className="project-chip"
      aria-label={`Active project: ${name ?? activeProjectId}`}
      title="Open the active project"
    >
      <span>Project</span>
      <strong>{name ?? 'open project'}</strong>
    </Link>
  )
}
