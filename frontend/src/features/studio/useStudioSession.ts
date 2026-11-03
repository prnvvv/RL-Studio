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
      else if (result.error.kind !== 'cancelled') setCatalog({ state: 'error', error: result.error })
    },
    [service],
  )

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
      if (busy !== null) return false
      const current = store.getState().status
      if (current !== null && ACTIVE_STATUSES.includes(current)) {
        setNotice({
          tone: 'warning',
          message: 'A session is active. Stop it before initializing another environment.',
        })
        return false
      }
      setBusy('initialize')
      setNotice(null)
      const result = await service.createSession({ ...config, ...(name ? { name } : {}) })
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
    [attach, busy, service, store],
  )

  const command = useCallback(
    async (name: SessionCommand) => {
      const sessionId = store.getState().sessionId
      if (sessionId === null || busy !== null) return
      setBusy(name)
      setNotice(null)
      const result = await service.command(sessionId, name)
      setBusy(null)
      if (result.state === 'error') {
        setNotice({ tone: 'error', message: describeFailure(`The ${name} request`, result.error) })
        return
      }
      store.applyCommandResult(result.data)
    },
    [busy, service, store],
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

  return { store, state, catalog, busy, notice, setNotice, initialize, command, setSpeed, reloadCatalog: loadCatalog, service }
}
