import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { setProjectScope } from '../services/projectScope'

const STORAGE_KEY = 'rl-studio.activeProject'
const PROJECT_ID = /^prj_[0-9a-f]{16}$/

interface ActiveProjectValue {
  /** The project the workspace is operating in, or `null` when none is open. */
  activeProjectId: string | null
  setActiveProjectId: (projectId: string | null) => void
}

const ActiveProjectContext = createContext<ActiveProjectValue>({
  activeProjectId: null,
  setActiveProjectId: () => {},
})

function readStored(): string | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY)
    return value !== null && PROJECT_ID.test(value) ? value : null
  } catch {
    return null // storage can be blocked or empty; the project page simply starts with no active project
  }
}

function writeStored(projectId: string | null): void {
  try {
    if (projectId === null) window.localStorage.removeItem(STORAGE_KEY)
    else window.localStorage.setItem(STORAGE_KEY, projectId)
  } catch {
    // Persistence is a convenience; the in-memory selection still works for this tab.
  }
}

/**
 * The active project survives navigation between modules and a browser refresh (it is stored per browser).
 * Direct links to `/projects/:projectId` also activate that project. The id is only ever a pointer: every
 * request is validated by the backend, which is what isolates one project's data from another's.
 */
export function ActiveProjectProvider({ children }: { children: ReactNode }) {
  const [activeProjectId, setState] = useState<string | null>(() => {
    const stored = readStored()
    setProjectScope(stored) // before any child can request data, so the very first request is already scoped
    return stored
  })

  const setActiveProjectId = useCallback((projectId: string | null) => {
    setProjectScope(projectId)
    setState(projectId)
    writeStored(projectId)
  }, [])

  const value = useMemo(
    () => ({ activeProjectId, setActiveProjectId }),
    [activeProjectId, setActiveProjectId],
  )
  return <ActiveProjectContext.Provider value={value}>{children}</ActiveProjectContext.Provider>
}

/** Safe without a provider (returns "no active project"), so isolated component tests keep working. */
export function useActiveProject(): ActiveProjectValue {
  return useContext(ActiveProjectContext)
}
