import { Component, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { useScenePalette } from './renderers/palette'
import { getRenderer } from './renderers/registry'
import { BrainPanel } from './BrainPanel'
import { StreamOverlay } from './StreamOverlay'
import { webglAvailable } from './webgl'
import { useFrameSnapshot } from './useFrameSnapshot'
import type { ViewMode } from './ControlToolbar'
import type { StudioStore } from './studioStore'
import type { FramePayload, SessionStatus } from './studioTypes'

export type { ViewMode }

interface Props {
  store: StudioStore
  /** Renderer key from the environment catalog (null when nothing is selected). */
  rendererKey: string | null
  scene: Record<string, unknown> | null
  environmentName: string | null
  status: SessionStatus | null
  /** True when `scene` comes from the catalog default, not an initialized session. */
  preview: boolean
  /** Bumped by the parent to reset the camera. */
  cameraResetNonce: number
  viewMode: ViewMode
  /** Key help shown while the human drives; null when the agent is in control. */
  manualHint?: string | null
  /** Show the live action-probability panel (the overlays draw themselves from frame data). */
  brainActive?: boolean
}

class CanvasBoundary extends Component<
  { children: ReactNode; fallback: ReactNode; resetKey: string },
  { failed: boolean }
> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidUpdate(prev: { resetKey: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.failed) this.setState({ failed: false })
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

function describeAction(action: FramePayload['action']): string {
  if (action === null || action === undefined) return '—'
  return Array.isArray(action) ? action.map((a) => a.toFixed(2)).join(', ') : String(action)
}

function Hud({
  store,
  status,
  preview,
}: {
  store: StudioStore
  status: SessionStatus | null
  preview: boolean
}) {
  const frame = useFrameSnapshot(store)
  const outcome = frame?.done ? frame.outcome : undefined
  const rows: Array<[string, string]> = [
    ['Status', preview ? 'preview' : (status ?? '—')],
    ['Episode', frame ? String(Math.max(frame.episode, 0)) : '—'],
    ['Episode step', frame ? String(frame.episode_step) : '—'],
    ['Reward', frame ? frame.episode_reward.toFixed(2) : '—'],
    ['Action', frame ? describeAction(frame.action) : '—'],
    ['Source', frame?.source ?? '—'],
  ]
  return (
    <div className="sim-hud" aria-label="Simulation readout">
      {rows.map(([label, value]) => (
        <div key={label} className="sim-hud__row">
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
      {outcome && (
        <div className={`sim-hud__outcome ${outcome.success ? 'is-good' : 'is-bad'}`} role="status">
          {outcome.success ? 'Success' : 'Terminated'}: {outcome.reason.replace(/_/g, ' ')}
        </div>
      )}
    </div>
  )
}

/**
 * The simulation viewport: draws the backend's environment state in 3D or 2D.
 * It contains no learning logic; it only renders `store.frame`.
 */
export function SimulationViewport({
  store,
  rendererKey,
  scene,
  environmentName,
  status,
  preview,
  cameraResetNonce,
  viewMode,
  manualHint = null,
  brainActive = false,
}: Props) {
  const palette = useScenePalette()
  const definition = getRenderer(rendererKey)
  const containerRef = useRef<HTMLDivElement>(null)
  const controlsRef = useRef<OrbitControlsImpl>(null)
  const [fullscreen, setFullscreen] = useState(false)
  const webgl = useMemo(() => webglAvailable(), [])

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === containerRef.current)
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  useEffect(() => {
    if (cameraResetNonce > 0) controlsRef.current?.reset()
  }, [cameraResetNonce])

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen()
    else void containerRef.current?.requestFullscreen?.()
  }, [])

  const camera = useMemo(() => definition?.camera(scene) ?? null, [definition, scene])
  const sceneKey = `${rendererKey}:${JSON.stringify(scene)}`
  const use3d = viewMode === '3d' && webgl && definition !== null

  const flat = definition ? (
    <definition.Scene2D scene={scene} store={store} palette={palette} />
  ) : null

  return (
    <div ref={containerRef} className="sim-viewport" data-fullscreen={fullscreen || undefined}>
      <div className="sim-viewport__toolbar" role="toolbar" aria-label="Viewport controls">
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => toggleFullscreen()}
          aria-pressed={fullscreen}
        >
          {fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
        </button>
      </div>

      {definition === null ? (
        <div className="sim-viewport__empty">
          <h3>{rendererKey ? 'No renderer for this environment' : 'No environment selected'}</h3>
          <p>
            {rendererKey
              ? `The backend environment "${environmentName ?? rendererKey}" has no registered renderer.`
              : 'Choose an agent and an environment, then initialize the sandbox.'}
          </p>
        </div>
      ) : use3d && camera ? (
        <CanvasBoundary resetKey={sceneKey} fallback={flat}>
          <Canvas
            key={sceneKey}
            camera={{ position: camera.position, fov: 45 }}
            dpr={[1, 2]}
            gl={{ antialias: true }}
          >
            <color attach="background" args={[palette.background]} />
            <definition.Scene3D scene={scene} store={store} palette={palette} />
            <OrbitControls
              ref={controlsRef}
              makeDefault
              target={camera.target}
              enableDamping
              maxPolarAngle={Math.PI * 0.49}
            />
          </Canvas>
        </CanvasBoundary>
      ) : (
        flat
      )}

      {definition !== null && (
        <>
          <StreamOverlay store={store} />
          {brainActive && <BrainPanel store={store} renderer={rendererKey} />}
          {manualHint !== null && (
            <div className="sim-manual" role="status">
              <strong>Manual control</strong> — {manualHint}
            </div>
          )}
          <Hud store={store} status={status} preview={preview} />
          <div className="sim-shortcuts" aria-hidden="true">
            <kbd>Space</kbd> pause / resume · <kbd>C</kbd> reset camera
          </div>
          {preview && (
            <div className="sim-viewport__badge" role="note">
              Preview — environment not initialized
            </div>
          )}
          {!webgl && viewMode === '3d' && (
            <div className="sim-viewport__badge sim-viewport__badge--warn" role="note">
              WebGL unavailable — showing the 2D view
            </div>
          )}
        </>
      )}
    </div>
  )
}
