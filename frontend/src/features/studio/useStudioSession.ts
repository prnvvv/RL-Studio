import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import {
  createStudioService,
  sessionStreamUrl,
  type SessionCommand,
  type StudioService,
} from '../../services/studio'
import type { ServiceError } from '../../services/types'
import { connectSession } from './studioConnection'
import { StudioStore } from './studioStore'
import { ACTIVE_STATUSES, type Catalog, type SessionConfig } from './studioTypes'

export type CatalogState =
  | { state: 'loading' }
  | { state: 'ready'; catalog: Catalog }
  | { state: 'error'; error: ServiceError }

export interface Notice {
  tone: 'info' | 'warning' | 'error'
  message: string
}

const defaultService = createStudioService()

const COMMAND_ERRORS: Record<string, string> = {
  conflict: 'That action is not allowed in the current session state.',
  not_found: 'The session no longer exists on the backend.',
}

function describeFailure(action: string, error: ServiceError): string {
  if (error.kind === 'timeout' || error.kind === 'network') {
    return `${action} did not complete and its outcome is unknown. ${error.message}`
  }
  return `${action} failed. ${COMMAND_ERRORS[error.kind] ?? error.message}`
}

/**
 * Owns the studio session for the workspace: catalog loading, creating and
 * attaching to a backend session, live streaming, and lifecycle commands.
 *
 * Lifecycle status is only ever taken from backend responses and the stream.
 */
export function useStudioSession(service: StudioService = defaultService) {
  const store = useMemo(() => new StudioStore(), [])
  const state = useSyncExternalStore(store.subscribe, store.getState)
  const [catalog, setCatalog] = useState<CatalogState>({ state: 'loading' })
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const disposeRef = useRef<(() => void) | null>(null)
  // Synchronous guard: React state updates are async, so a fast double click could
  // otherwise send the same command twice before `busy` re-renders.
  const busyRef = useRef<string | null>(null)

  const attach = useCallback(
    (sessionId: string) => {
      disposeRef.current?.()
      disposeRef.current = connectSession(store, {
        url: (after) => sessionStreamUrl(sessionId, after),
      })
    },
    [store],
  )

  const loadCatalog = useCallback(
    async (signal?: AbortSignal) => {
      setCatalog({ state: 'loading' })
      const result = await service.getCatalog(signal)
      if (signal?.aborted) return
      if (result.state === 'ok') setCatalog({ state: 'ready', catalog: result.data })
      else if (result.error.kind !== 'cancelled')
        setCatalog({ state: 'error', error: result.error })
    },
    [service],
  )

  /** Reload the catalog without the loading screen (used after uploads). Returns the fresh catalog. */
  const refreshCatalog = useCallback(async (): Promise<Catalog | null> => {
    const result = await service.getCatalog()
    if (result.state !== 'ok') return null
    setCatalog({ state: 'ready', catalog: result.data })
    return result.data
  }, [service])

  // Catalog, then re-attach to a session that is still training so a page
  // refresh never orphans a running experiment.
  useEffect(() => {
    const controller = new AbortController()
    void loadCatalog(controller.signal)
    void (async () => {
      const sessions = await service.listSessions(controller.signal)
      if (controller.signal.aborted || sessions.state !== 'ok') return
      const active = sessions.data.find((s) => ACTIVE_STATUSES.includes(s.status))
      if (active) {
        setNotice({
          tone: 'info',
          message: `Re-attached to the session "${active.name}", which is still ${active.status}.`,
        })
        attach(active.session_id)
      }
    })()
    return () => controller.abort()
  }, [service, loadCatalog, attach])

  useEffect(
    () => () => {
      disposeRef.current?.()
      disposeRef.current = null
    },
    [],
  )

  const initialize = useCallback(
    async (config: SessionConfig, name?: string) => {
      if (busyRef.current !== null) return false
      const current = store.getState().status
      if (current !== null && ACTIVE_STATUSES.includes(current)) {
        setNotice({
          tone: 'warning',
          message: 'A session is active. Stop it before initializing another environment.',
        })
        return false
      }
      busyRef.current = 'initialize'
      setBusy('initialize')
      setNotice(null)
      const result = await service.createSession({ ...config, ...(name ? { name } : {}) })
      busyRef.current = null
      setBusy(null)
      if (result.state === 'error') {
        setNotice({ tone: 'error', message: describeFailure('Initialization', result.error) })
        return false
      }
      disposeRef.current?.()
      store.clear()
      store.applySnapshot(result.data)
      attach(result.data.session_id)
      return true
    },
    [attach, service, store],
  )

  const command = useCallback(
    async (name: SessionCommand): Promise<boolean> => {
      const sessionId = store.getState().sessionId
      if (sessionId === null || busyRef.current !== null) return false
      busyRef.current = name
      setBusy(name)
      setNotice(null)
      const result = await service.command(sessionId, name)
      busyRef.current = null
      setBusy(null)
      if (result.state === 'error') {
        setNotice({ tone: 'error', message: describeFailure(`The ${name} request`, result.error) })
        return false
      }
      store.applyCommandResult(result.data)
      return true
    },
    [service, store],
  )

  const setManualControl = useCallback(
    async (active: boolean): Promise<boolean> => {
      const sessionId = store.getState().sessionId
      if (sessionId === null) return false
      const result = await service.setControl(sessionId, active)
      if (result.state === 'error') {
        setNotice({
          tone: 'error',
          message: describeFailure('Changing manual control', result.error),
        })
        return false
      }
      return true
    },
    [service, store],
  )

  const sendAction = useCallback(
    (action: number) => store.send({ type: 'action', action }),
    [store],
  )

  const setSpeed = useCallback(
    async (speed: number) => {
      const sessionId = store.getState().sessionId
      if (sessionId === null) return
      const result = await service.setSpeed(sessionId, speed)
      if (result.state === 'error') {
        setNotice({ tone: 'error', message: describeFailure('Changing speed', result.error) })
      }
    },
    [service, store],
  )

  return {
    store,
    state,
    catalog,
    busy,
    notice,
    setNotice,
    initialize,
    command,
    setSpeed,
    setManualControl,
    sendAction,
    reloadCatalog: loadCatalog,
    refreshCatalog,
    service,
  }
}
