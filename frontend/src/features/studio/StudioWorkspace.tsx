import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from 'react'
import { Link } from 'react-router-dom'
import { ThemeToggle } from '../../components/ThemeToggle'
import { ConfigPanel } from './ConfigPanel'
import { ControlToolbar, type ViewMode } from './ControlToolbar'
import { ExperimentsPanel } from './ExperimentsPanel'
import { LibraryPanel, type RemoveTarget } from './LibraryPanel'
import { LogConsole } from './LogConsole'
import { MetricsPanel } from './MetricsPanel'
import { SimulationViewport } from './SimulationViewport'
import { webglAvailable } from './webgl'
import { ToastProvider } from './toast'
import { useToast } from './toastState'
import type { UploadHooks, UploadOutcome } from './UploadDropzone'
import {
  controlAvailability,
  emptyDraft,
  findAgent,
  findEnvironment,
  incompatibilityReason,
  selectAgent,
  selectEnvironment,
  toSessionConfig,
  validateDraft,
  type Draft,
} from './studioConfig'
import { ACTIVE_STATUSES, type Catalog, type ParamValue } from './studioTypes'
import type { SessionCommand } from '../../services/studio'
import { useStudioSession } from './useStudioSession'
import './studio.css'
import './studio.ux.css'

type LeftTab = 'library' | 'configure'
type DockTab = 'metrics' | 'logs' | 'experiments'

const LAYOUT_KEY = 'rl-studio-workspace-layout'
const MIN_LEFT = 280
const MIN_DOCK = 120

function loadLayout(): { left: number; dock: number } {
  try {
    const raw = window.localStorage.getItem(LAYOUT_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as { left?: number; dock?: number }
      if (typeof parsed.left === 'number' && typeof parsed.dock === 'number') {
        return { left: parsed.left, dock: parsed.dock }
      }
    }
  } catch {
    // Storage unavailable or corrupt: fall back to defaults.
  }
  return { left: Math.round(window.innerWidth * 0.35), dock: 300 }
}

function saveLayout(layout: { left: number; dock: number }) {
  try {
    window.localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout))
  } catch {
    // Persisting layout is a convenience only.
  }
}

function sameConfig(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

function ConnectionLabel({ connection }: { connection: string }) {
  const text: Record<string, string> = {
    idle: 'not connected',
    connecting: 'connecting…',
    live: 'live',
    reconnecting: 'reconnecting…',
    closed: 'disconnected',
  }
  return <span className="studio-header__session">stream: {text[connection] ?? connection}</span>
}

type Session = ReturnType<typeof useStudioSession>

const COMMAND_TOASTS: Record<SessionCommand, string> = {
  start: 'Training started',
  pause: 'Pause requested',
  resume: 'Training resumed',
  stop: 'Stop requested',
  reset: 'Session reset',
}

/** Keys that must keep their normal meaning in these elements (typing, native button activation). */
function shortcutsSuppressed(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  if (['INPUT', 'TEXTAREA', 'SELECT', 'A', 'SUMMARY'].includes(target.tagName)) return true
  if (['tab', 'radio', 'separator', 'slider'].includes(target.getAttribute('role') ?? ''))
    return true
  // A focused button keeps its own Space behaviour, except inside the training toolbar.
  return target.tagName === 'BUTTON' && target.closest('.control-bar') === null
}

function WorkspaceBody({ catalog, session }: { catalog: Catalog; session: Session }) {
  const { state, store, busy, notice } = session
  const toast = useToast()
  const webgl = useMemo(() => webglAvailable(), [])
  const autoSwitched = useRef(false)
  const previousConnection = useRef(state.connection)
  const [draft, setDraft] = useState<Draft>(() => emptyDraft(catalog))
  const [leftTab, setLeftTab] = useState<LeftTab>('library')
  const [dockTab, setDockTab] = useState<DockTab>('metrics')
  const [viewMode, setViewMode] = useState<ViewMode>('3d')
  const [cameraNonce, setCameraNonce] = useState(0)
  const [layout, setLayout] = useState(loadLayout)
  const dragRef = useRef<{ kind: 'left' | 'dock'; start: number; origin: number } | null>(null)

  const active = state.status !== null && ACTIVE_STATUSES.includes(state.status)
  const errors = useMemo(() => validateDraft(catalog, draft), [catalog, draft])
  const mismatch = incompatibilityReason(catalog, draft.agent, draft.environment)
  const ready =
    draft.agent !== null &&
    draft.environment !== null &&
    mismatch === null &&
    Object.keys(errors).length === 0
  const initializeHint =
    !draft.agent || !draft.environment
      ? 'Select an agent and an environment first'
      : (mismatch ??
        (Object.keys(errors).length > 0 ? 'Fix the highlighted configuration fields' : null))
  const availability = controlAvailability(state.status, state.pendingCommand, ready)

  // Which environment the viewport shows: the session's, else the current selection (preview).
  const sessionEnv = findEnvironment(catalog, state.config?.environment ?? null)
  const previewEnv = findEnvironment(catalog, draft.environment)
  const viewEnv = state.sessionId !== null ? sessionEnv : previewEnv
  const viewScene = state.sessionId !== null ? state.scene : (previewEnv?.default_scene ?? null)
  const draftDiffers =
    state.config !== null && !active && !sameConfig(toSessionConfig(draft), state.config)

  const speed = state.progress?.speed ?? Number(draft.training.simulation_speed ?? 1)

  const changeParam = useCallback(
    (scope: 'agent_params' | 'env_params' | 'training', key: string, value: ParamValue) =>
      setDraft((current) => ({ ...current, [scope]: { ...current[scope], [key]: value } })),
    [],
  )

  const initialize = async () => {
    const config = toSessionConfig(draft)
    if (config === null || !ready) return
    const ok = await session.initialize(config)
    if (ok) {
      setCameraNonce((n) => n + 1)
      toast.push('success', 'Session initialized')
    }
  }

  const runCommand = useCallback(
    async (command: SessionCommand) => {
      const ok = await session.command(command)
      if (ok) toast.push('success', COMMAND_TOASTS[command])
    },
    [session, toast],
  )

  // Choosing both an agent and an environment moves the user on to configuration, once.
  const choose = (kind: 'agent' | 'environment', key: string) => {
    const next =
      kind === 'agent' ? selectAgent(catalog, draft, key) : selectEnvironment(catalog, draft, key)
    setDraft(next)
    if (!autoSwitched.current && next.agent !== null && next.environment !== null) {
      autoSwitched.current = true
      setLeftTab('configure')
    }
  }

  const uploadModel = async (file: File, hooks: UploadHooks): Promise<UploadOutcome> => {
    const result = await session.service.uploadModel(file, hooks)
    if (result.state === 'error') {
      toast.push('error', `Model upload failed. ${result.error.message}`)
      return { ok: false, message: result.error.message }
    }
    const { model, duplicate } = result.data
    const fresh = await session.refreshCatalog()
    if (fresh) setDraft((d) => selectAgent(fresh, d, model.key))
    toast.push(
      'success',
      duplicate ? `"${model.name}" was already in your library` : 'Model uploaded successfully',
    )
    return {
      ok: true,
      message: `${model.name} · ${model.algorithm}, ${model.obs_dim} inputs → ${model.action_dim} ${model.action_type} actions${duplicate ? ' (already in library)' : ''}`,
    }
  }

  const uploadEnvironment = async (file: File, hooks: UploadHooks): Promise<UploadOutcome> => {
    const result = await session.service.uploadEnvironment(file, hooks)
    if (result.state === 'error') {
      toast.push('error', `Environment upload failed. ${result.error.message}`)
      return { ok: false, message: result.error.message }
    }
    const { environment, duplicate } = result.data
    const fresh = await session.refreshCatalog()
    if (fresh) setDraft((d) => selectEnvironment(fresh, d, environment.key))
    toast.push(
      'success',
      duplicate
        ? `"${environment.name}" was already in your library`
        : 'Environment uploaded successfully',
    )
    return {
      ok: true,
      message: `${environment.name} · ${environment.layout.rows}×${environment.layout.cols} grid${duplicate ? ' (already in library)' : ''}`,
    }
  }

  const removeCustom = async (target: RemoveTarget) => {
    const result =
      target.kind === 'model'
        ? await session.service.deleteModel(target.id)
        : await session.service.deleteEnvironment(target.id)
    if (result.state === 'error') {
      toast.push('error', `Could not remove "${target.name}". ${result.error.message}`)
      return
    }
    await session.refreshCatalog()
    setDraft((d) =>
      target.kind === 'model' && d.agent === target.key
        ? { ...d, agent: null, agent_params: {} }
        : target.kind === 'environment' && d.environment === target.key
          ? { ...d, environment: null, env_params: {} }
          : d,
    )
    toast.push('success', `Removed "${target.name}"`)
  }

  // Transient notices become toasts instead of a banner that has to be cleared.
  useEffect(() => {
    if (notice) toast.push(notice.tone, notice.message)
  }, [notice, toast])

  // Connection changes for an attached session.
  useEffect(() => {
    const previous = previousConnection.current
    previousConnection.current = state.connection
    if (state.sessionId === null) return
    if (state.connection === 'reconnecting' && previous === 'live') {
      toast.push('warning', 'Lost the connection to the training session. Reconnecting…')
    } else if (state.connection === 'live' && previous === 'reconnecting') {
      toast.push('success', 'Reconnected to the training session')
    } else if (state.connection === 'closed' && previous !== 'closed' && previous !== 'idle') {
      toast.push('error', 'Failed to connect to the training session')
    }
  }, [state.connection, state.sessionId, toast])

  // Space pauses or resumes; C resets the camera.
  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || event.repeat)
        return
      if (shortcutsSuppressed(event.target)) return
      if (event.code === 'Space' || event.key === ' ') {
        if (availability.pause && busy === null) {
          event.preventDefault()
          void runCommand('pause')
        } else if (availability.resume && busy === null) {
          event.preventDefault()
          void runCommand('resume')
        }
      } else if (event.key === 'c' || event.key === 'C') {
        setCameraNonce((n) => n + 1)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [availability.pause, availability.resume, busy, runCommand])

  const onSpeed = (value: number) => {
    changeParam('training', 'simulation_speed', value)
    if (state.sessionId !== null) void session.setSpeed(value)
  }

  // Pointer-driven resizing for the vertical and horizontal splitters.
  const onPointerDown = (kind: 'left' | 'dock') => (event: PointerEvent<HTMLElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId)
    dragRef.current = {
      kind,
      start: kind === 'left' ? event.clientX : event.clientY,
      origin: kind === 'left' ? layout.left : layout.dock,
    }
  }
  const onPointerMove = (event: PointerEvent<HTMLElement>) => {
    const drag = dragRef.current
    if (!drag) return
    if (drag.kind === 'left') {
      const next = Math.min(
        Math.max(drag.origin + (event.clientX - drag.start), MIN_LEFT),
        window.innerWidth * 0.6,
      )
      setLayout((l) => ({ ...l, left: next }))
    } else {
      const next = Math.min(
        Math.max(drag.origin - (event.clientY - drag.start), MIN_DOCK),
        window.innerHeight * 0.7,
      )
      setLayout((l) => ({ ...l, dock: next }))
    }
  }
  const onPointerUp = () => {
    dragRef.current = null
    saveLayout(layout)
  }
  const onKey = (kind: 'left' | 'dock') => (event: KeyboardEvent<HTMLElement>) => {
    const step = event.shiftKey ? 80 : 24
    const delta =
      event.key === 'ArrowRight' || event.key === 'ArrowUp'
        ? step
        : event.key === 'ArrowLeft' || event.key === 'ArrowDown'
          ? -step
          : 0
    if (delta === 0) return
    event.preventDefault()
    setLayout((l) => {
      const next =
        kind === 'left'
          ? { ...l, left: Math.max(MIN_LEFT, l.left + delta) }
          : { ...l, dock: Math.max(MIN_DOCK, l.dock + delta) }
      saveLayout(next)
      return next
    })
  }

  useEffect(() => {
    // Keep the layout within the viewport when the window shrinks.
    const onResize = () =>
      setLayout((l) => ({ ...l, left: Math.min(l.left, window.innerWidth * 0.6) }))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  return (
    <div className="studio">
      <header className="studio-header">
        <div className="studio-header__left">
          <Link to="/" className="studio-header__brand">
            RL Studio
          </Link>
          <span className="studio-header__session">{state.name ?? 'No session'}</span>
          <ConnectionLabel connection={state.connection} />
        </div>
        <nav className="studio-header__right" aria-label="Studio navigation">
          <Link to="/monitoring">Monitoring</Link>
          <Link to="/diagnosis-recovery">Diagnosis &amp; Recovery</Link>
          <Link to="/reports">Reports</Link>
          <ThemeToggle />
        </nav>
      </header>

      <div className="studio-body">
        <aside className="studio-left" style={{ width: layout.left }} aria-label="Configuration">
          <div className="tabs" role="tablist" aria-label="Configuration sections">
            {(['library', 'configure'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={leftTab === tab}
                onClick={() => setLeftTab(tab)}
              >
                {tab === 'library' ? 'Agents & environments' : 'Configure'}
              </button>
            ))}
          </div>
          <div className="tab-body" role="tabpanel">
            {leftTab === 'library' ? (
              <LibraryPanel
                catalog={catalog}
                draft={draft}
                locked={active}
                onSelectAgent={(key) => choose('agent', key)}
                onSelectEnvironment={(key) => choose('environment', key)}
                onConfigure={() => setLeftTab('configure')}
                uploadModel={uploadModel}
                uploadEnvironment={uploadEnvironment}
                onRemove={removeCustom}
              />
            ) : (
              <ConfigPanel
                catalog={catalog}
                draft={draft}
                errors={errors}
                disabled={active}
                onChange={changeParam}
              />
            )}
          </div>
        </aside>
        <div
          className="studio-splitter"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize configuration panel"
          tabIndex={0}
          onPointerDown={onPointerDown('left')}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onKeyDown={onKey('left')}
        />

        <section className="studio-right" aria-label="Simulation sandbox">
          <ControlToolbar
            availability={availability}
            status={state.status}
            pendingCommand={state.pendingCommand}
            busy={busy}
            speed={speed}
            initializeHint={initializeHint}
            viewMode={viewMode}
            webgl={webgl}
            onInitialize={() => void initialize()}
            onCommand={(command) => void runCommand(command)}
            onSpeed={onSpeed}
            onResetCamera={() => setCameraNonce((n) => n + 1)}
            onViewModeChange={setViewMode}
          />
          {state.error && (
            <p
              className="note note--error"
              role="alert"
              style={{ margin: 'var(--space-2) var(--space-3)' }}
            >
              {state.error}
            </p>
          )}
          {draftDiffers && (
            <p className="note" role="status" style={{ margin: 'var(--space-2) var(--space-3)' }}>
              The configuration on the left differs from the initialized session. Initialize again
              to apply it.
            </p>
          )}

          <SimulationViewport
            store={store}
            rendererKey={viewEnv?.renderer ?? null}
            scene={viewScene}
            environmentName={viewEnv?.name ?? null}
            status={state.status}
            preview={state.sessionId === null}
            cameraResetNonce={cameraNonce}
            viewMode={viewMode}
          />

          <div className="dock" style={{ ['--dock-height' as string]: `${layout.dock}px` }}>
            <div
              className="dock-handle"
              role="separator"
              aria-orientation="horizontal"
              aria-label="Resize monitoring dock"
              tabIndex={0}
              onPointerDown={onPointerDown('dock')}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onKeyDown={onKey('dock')}
            />
            <div className="tabs" role="tablist" aria-label="Monitoring sections">
              {(
                [
                  ['metrics', 'Metrics'],
                  ['logs', `Logs (${state.logs.length})`],
                  ['experiments', 'Experiments'],
                ] as const
              ).map(([tab, label]) => (
                <button
                  key={tab}
                  type="button"
                  role="tab"
                  aria-selected={dockTab === tab}
                  onClick={() => setDockTab(tab)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="tab-body" role="tabpanel">
              {dockTab === 'metrics' && (
                <MetricsPanel
                  state={state}
                  agent={findAgent(catalog, state.config?.agent ?? draft.agent)}
                />
              )}
              {dockTab === 'logs' && <LogConsole logs={state.logs} />}
              {dockTab === 'experiments' && (
                <ExperimentsPanel service={session.service} state={state} />
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

/** Full-viewport training workspace entered from "Open Studio". */
export function StudioWorkspace() {
  return (
    <ToastProvider>
      <StudioWorkspaceContent />
    </ToastProvider>
  )
}

function StudioWorkspaceContent() {
  const session = useStudioSession()
  if (session.catalog.state === 'loading') {
    return (
      <div className="studio" role="status" aria-busy="true">
        <div className="empty" style={{ margin: 'auto' }}>
          Loading agents and environments from the backend…
        </div>
      </div>
    )
  }
  if (session.catalog.state === 'error') {
    return (
      <div className="studio">
        <div className="empty" style={{ margin: 'auto', maxWidth: 420 }} role="alert">
          <h2 style={{ color: 'var(--text-primary)' }}>The studio backend is unavailable</h2>
          <p>
            {session.catalog.error.message} No agents or environments are listed because none can be
            run right now.
          </p>
          <button type="button" className="btn" onClick={() => void session.reloadCatalog()}>
            Retry
          </button>
          <p>
            <Link to="/">Back to home</Link>
          </p>
        </div>
      </div>
    )
  }
  return <WorkspaceBody catalog={session.catalog.catalog} session={session} />
}
