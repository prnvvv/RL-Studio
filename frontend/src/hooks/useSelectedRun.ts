import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useActiveProject } from '../contexts/ActiveProjectContext'
import {
  createTrainingHistoryService,
  type RunDetail,
  type TrainingHistoryService,
  type TrainingRun,
} from '../services/trainingHistory'

export type SelectedRunStatus =
  /** No project is open, so there is no history to resolve. */
  | 'no-project'
  | 'loading'
  | 'ready'
  /** The project has no training runs yet. */
  | 'empty'
  /** The run in the URL does not exist in this project (or is not accessible). */
  | 'invalid'
  | 'error'

export interface SelectedRun {
  projectId: string | null
  runId: string | null
  /** Full persisted detail of the selected run (null until loaded or when unavailable). */
  detail: RunDetail | null
  run: TrainingRun | null
  /** The project's most recent runs, newest first, for the selector. */
  runs: TrainingRun[]
  status: SelectedRunStatus
  select: (runId: string) => void
  /** Drop an invalid or stale selection and use the project's latest run. */
  useLatest: () => void
  reload: () => void
}

const STORE_PREFIX = 'rl-studio.selectedRun.'
const LIST_SIZE = 100
const ACTIVE_POLL_MS = 3000

function readStored(projectId: string): string | null {
  try {
    return window.localStorage.getItem(STORE_PREFIX + projectId)
  } catch {
    return null // a convenience only: the URL and the backend's latest run still resolve the selection
  }
}

function writeStored(projectId: string, runId: string): void {
  try {
    window.localStorage.setItem(STORE_PREFIX + projectId, runId)
  } catch {
    // not persisted; the in-URL selection still works for this tab
  }
}

/**
 * The single source of "which training run is this page about".
 *
 * Resolution order: the `?runId=` in the URL (so deep links, refresh and back/forward work), else the run last
 * selected in this project (remembered per browser, validated against the backend), else the project's latest run.
 * The resolved id is written back into the URL, so the page is always a shareable link. The backend remains the
 * authority: an id that is not in the active project comes back as `invalid`, never as another project's data.
 */
export function useSelectedRun(service?: TrainingHistoryService): SelectedRun {
  const { activeProjectId: projectId } = useActiveProject()
  const [params, setParams] = useSearchParams()
  const api = useMemo(() => service ?? createTrainingHistoryService(), [service])
  const urlRun = params.get('runId')?.trim() || null

  const [runs, setRuns] = useState<TrainingRun[]>([])
  const [listState, setListState] = useState<'loading' | 'ok' | 'error'>('loading')
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [detailState, setDetailState] = useState<'idle' | 'loading' | 'ok' | 'invalid' | 'error'>(
    'idle',
  )
  const [nonce, setNonce] = useState(0)
  const paramsRef = useRef(params)
  paramsRef.current = params

  const writeRun = useCallback(
    (runId: string, replace: boolean) => {
      const next = new URLSearchParams(paramsRef.current)
      next.set('runId', runId)
      setParams(next, { replace })
      if (projectId !== null) writeStored(projectId, runId)
    },
    [projectId, setParams],
  )

  // The project's recent runs (selector + latest-run fallback).
  useEffect(() => {
    if (projectId === null) return
    const controller = new AbortController()
    setListState('loading')
    void api
      .listRuns(projectId, { sort: 'recent', limit: LIST_SIZE }, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        if (result.state === 'ok') {
          setRuns(result.data.items)
          setListState('ok')
        } else {
          setListState('error')
        }
      })
    return () => controller.abort()
  }, [api, projectId, nonce])

  // No run in the URL: adopt the remembered run if it still exists, else the latest one.
  useEffect(() => {
    if (projectId === null || urlRun !== null || listState !== 'ok' || runs.length === 0) return
    const remembered = readStored(projectId)
    const chosen = runs.find((r) => r.run_id === remembered) ?? runs[0]
    if (chosen) writeRun(chosen.run_id, true)
  }, [projectId, urlRun, listState, runs, writeRun])

  // The selected run's persisted detail; polled only while that run is actually active.
  useEffect(() => {
    if (projectId === null || urlRun === null) {
      setDetail(null)
      setDetailState('idle')
      return
    }
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    async function load(first: boolean) {
      if (first) setDetailState('loading')
      const result = await api.getRun(projectId as string, urlRun as string, controller.signal)
      if (controller.signal.aborted) return
      if (result.state === 'ok') {
        setDetail(result.data)
        setDetailState('ok')
        if (result.data.run.active) timer = setTimeout(() => void load(false), ACTIVE_POLL_MS)
      } else if (result.error.kind === 'not_found') {
        setDetail(null)
        setDetailState('invalid')
      } else if (first) {
        setDetail(null)
        setDetailState('error')
      } else {
        timer = setTimeout(() => void load(false), ACTIVE_POLL_MS * 2) // keep the last known state; retry later
      }
    }
    setDetail(null)
    void load(true)
    return () => {
      controller.abort()
      if (timer !== undefined) clearTimeout(timer)
    }
  }, [api, projectId, urlRun, nonce])

  const status: SelectedRunStatus = useMemo(() => {
    if (projectId === null) return 'no-project'
    if (urlRun !== null) {
      if (detailState === 'invalid') return 'invalid'
      if (detailState === 'error') return 'error'
      return detailState === 'ok' ? 'ready' : 'loading'
    }
    if (listState === 'loading') return 'loading'
    if (listState === 'error') return 'error'
    return runs.length === 0 ? 'empty' : 'loading'
  }, [projectId, urlRun, detailState, listState, runs.length])

  return {
    projectId,
    runId: urlRun,
    detail,
    run: detail?.run ?? null,
    runs,
    status,
    select: (runId) => writeRun(runId, false),
    useLatest: () => {
      const latest = runs[0]
      if (latest) writeRun(latest.run_id, true)
      else {
        const next = new URLSearchParams(paramsRef.current)
        next.delete('runId')
        setParams(next, { replace: true })
      }
    },
    reload: () => setNonce((n) => n + 1),
  }
}
