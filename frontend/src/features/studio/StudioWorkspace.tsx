import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { Link } from 'react-router-dom'
import { ThemeToggle } from '../../components/ThemeToggle'
import { ConfigPanel } from './ConfigPanel'
import { ControlToolbar } from './ControlToolbar'
import { ExperimentsPanel } from './ExperimentsPanel'
import { LibraryPanel } from './LibraryPanel'
import { LogConsole } from './LogConsole'
import { MetricsPanel } from './MetricsPanel'
import { SimulationViewport, type ViewMode } from './SimulationViewport'
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
import { useStudioSession } from './useStudioSession'
import './studio.css'

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

function WorkspaceBody({ catalog, session }: { catalog: Catalog; session: Session }) {
  const { state, store, busy, notice } = session
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
  const ready = draft.agent !== null && draft.environment !== null && mismatch === null && Object.keys(errors).length === 0
  const initializeHint = !draft.agent || !draft.environment
    ? 'Select an agent and an environment first'
    : mismatch ?? (Object.keys(errors).length > 0 ? 'Fix the highlighted configuration fields' : null)
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
    if (ok) setCameraNonce((n) => n + 1)
  }

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
      const next = Math.min(Math.max(drag.origin + (event.clientX - drag.start), MIN_LEFT), window.innerWidth * 0.6)
      setLayout((l) => ({ ...l, left: next }))
    } else {
      const next = Math.min(Math.max(drag.origin - (event.clientY - drag.start), MIN_DOCK), window.innerHeight * 0.7)
      setLayout((l) => ({ ...l, dock: next }))
    }
  }
  const onPointerUp = () => {
    dragRef.current = null
    saveLayout(layout)
  }
  const onKey = (kind: 'left' | 'dock') => (event: KeyboardEvent<HTMLElement>) => {
    const step = event.shiftKey ? 80 : 24
    const delta = event.key === 'ArrowRight' || event.key === 'ArrowUp' ? step : event.key === 'ArrowLeft' || event.key === 'ArrowDown' ? -step : 0
    if (delta === 0) return
    event.preventDefault()
    setLayout((l) => {
      const next = kind === 'left' ? { ...l, left: Math.max(MIN_LEFT, l.left + delta) } : { ...l, dock: Math.max(MIN_DOCK, l.dock + delta) }
      saveLayout(next)
      return next
    })
  }

  useEffect(() => {
    // Keep the layout within the viewport when the window shrinks.
    const onResize = () => setLayout((l) => ({ ...l, left: Math.min(l.left, window.innerWidth * 0.6) }))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  return (
    <div className="studio">
      <header className="studio-header">
        <div className="studio-header__left">
          <Link to="/" className="studio-header__brand">RL Studio</Link>
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
              <button key={tab} type="button" role="tab" aria-selected={leftTab === tab} onClick={() => setLeftTab(tab)}>
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
                onSelectAgent={(key) => setDraft((d) => selectAgent(catalog, d, key))}
                onSelectEnvironment={(key) => setDraft((d) => selectEnvironment(catalog, d, key))}
              />
            ) : (
              <ConfigPanel catalog={catalog} draft={draft} errors={errors} disabled={active} onChange={changeParam} />
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
            onInitialize={() => void initialize()}
            onCommand={(command) => void session.command(command)}
            onSpeed={onSpeed}
            onResetCamera={() => setCameraNonce((n) => n + 1)}
          />
          {notice && (
            <p className={`note${notice.tone === 'error' ? ' note--error' : ''}`} role={notice.tone === 'error' ? 'alert' : 'status'} style={{ margin: 'var(--space-2) var(--space-3)' }}>
              {notice.message}
            </p>
          )}
          {state.error && (
            <p className="note note--error" role="alert" style={{ margin: 'var(--space-2) var(--space-3)' }}>
              {state.error}
            </p>
          )}
          {draftDiffers && (
            <p className="note" role="status" style={{ margin: 'var(--space-2) var(--space-3)' }}>
              The configuration on the left differs from the initialized session. Initialize again to apply it.
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
            onViewModeChange={setViewMode}
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
                <button key={tab} type="button" role="tab" aria-selected={dockTab === tab} onClick={() => setDockTab(tab)}>
                  {label}
                </button>
              ))}
            </div>
            <div className="tab-body" role="tabpanel">
              {dockTab === 'metrics' && <MetricsPanel state={state} agent={findAgent(catalog, state.config?.agent ?? draft.agent)} />}
              {dockTab === 'logs' && <LogConsole logs={state.logs} />}
              {dockTab === 'experiments' && <ExperimentsPanel service={session.service} state={state} />}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

/** Full-viewport training workspace entered from "Open Studio". */
export function StudioWorkspace() {
  const session = useStudioSession()
  if (session.catalog.state === 'loading') {
    return (
      <div className="studio" role="status" aria-busy="true">
        <div className="empty" style={{ margin: 'auto' }}>Loading agents and environments from the backend…</div>
      </div>
    )
  }
  if (session.catalog.state === 'error') {
    return (
      <div className="studio">
        <div className="empty" style={{ margin: 'auto', maxWidth: 420 }} role="alert">
          <h2 style={{ color: 'var(--text-primary)' }}>The studio backend is unavailable</h2>
          <p>{session.catalog.error.message} No agents or environments are listed because none can be run right now.</p>
          <button type="button" className="btn" onClick={() => void session.reloadCatalog()}>
            Retry
          </button>
          <p><Link to="/">Back to home</Link></p>
        </div>
      </div>
    )
  }
  return <WorkspaceBody catalog={session.catalog.catalog} session={session} />
}
