// Owns the canvas, picks a rendering backend and keeps the failure mode loud:
// WebGL is tried first; if it cannot be created, fails to compile, draws
// nothing, or loses its context for good, a console.error explains why and the
// scene switches to a Canvas 2D render of the same layout.
//
// A canvas that has produced a WebGL context can never hand out a 2D context,
// so the fallback always mounts a fresh canvas element in the host.

import type { BackendCallbacks, BackendKind, RenderBackend } from './backendTypes'
import { createCanvas2DBackend } from './canvas2dBackend'
import type { Point } from './sceneGeometry'
import { SceneState } from './sceneState'
import { createWebGLBackend } from './webglBackend'

const CONTEXT_RESTORE_TIMEOUT_MS = 3000
const STATS_INTERVAL_MS = 500
/** The 2D fallback is capped well below the WebGL particle count. */
const FALLBACK_MAX_DENSITY = 0.14

export interface SceneStats {
  backend: BackendKind | 'none'
  fps: number
  /** JS time spent in the draw call per frame (not GPU time). */
  frameMs: number
  /** Spring-physics step time per frame. */
  stepMs: number
  particles: number
  agent: Point
}

export interface SceneRendererOptions {
  density: number
  maxDpr: number
  reducedMotion: boolean
  touch: boolean
  /** Verbose diagnostics: GL info, sizes, errors, readback result. */
  debug?: boolean
  /** Terrain-style block rise on hover (default true); false restores the plain repel. */
  terrain?: boolean
  /** Skip WebGL (for verifying the fallback, `?renderer=2d`). */
  forceCanvas2D?: boolean
  onStats?: (stats: SceneStats) => void
}

export interface SceneRenderer {
  readonly backend: BackendKind | 'none'
  setPointer(point: Point | null): void
  setHazardHover(hovered: boolean): void
  /** Re-measure the host element and resize the canvas. */
  resize(): void
  start(): void
  stop(): void
  dispose(): void
}

export function createSceneRenderer(
  host: HTMLElement,
  options: SceneRendererOptions,
): SceneRenderer {
  const debug = Boolean(options.debug)
  const log = (...args: unknown[]) => {
    // eslint-disable-next-line no-console -- opt-in diagnostics behind ?debug=1
    if (debug) console.info('[landing-scene]', ...args)
  }
  const state = new SceneState({ reducedMotion: options.reducedMotion, touch: options.touch })
  const motion = !options.reducedMotion

  let canvas: HTMLCanvasElement | null = null
  let backend: RenderBackend | null = null
  let running = false
  let disposed = false
  let frame = 0
  let restoreTimer: ReturnType<typeof setTimeout> | undefined

  let statFrames = 0
  let statWindowStart = 0
  let statDrawMs = 0
  let statStepMs = 0
  let tickCount = 0
  let loggedAssembled = false

  function mountCanvas(): HTMLCanvasElement {
    canvas?.remove()
    const next = document.createElement('canvas')
    next.className = 'ls-scene__canvas'
    host.appendChild(next)
    canvas = next
    return next
  }

  const callbacks: BackendCallbacks = {
    onProblem(reason, fatal) {
      console.error(`[landing-scene] WebGL problem: ${reason}`)
      if (fatal) fallbackTo2D(reason)
    },
    onContextLost() {
      clearTimeout(restoreTimer)
      restoreTimer = setTimeout(
        () => fallbackTo2D(`WebGL context was not restored within ${CONTEXT_RESTORE_TIMEOUT_MS}ms`),
        CONTEXT_RESTORE_TIMEOUT_MS,
      )
    },
    onContextRestored() {
      clearTimeout(restoreTimer)
      applySize()
    },
  }

  function backendOptions(density: number) {
    return { density, terrain: options.terrain !== false, motion, debug, log, callbacks }
  }

  function drawStatic() {
    if (!backend) return
    state.setStatic()
    backend.draw(state, 0)
  }

  function applySize() {
    if (!backend) return
    const rect = host.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) {
      log('resize skipped: host has no size', { width: rect.width, height: rect.height })
      return
    }
    const dpr = Math.min(window.devicePixelRatio || 1, options.maxDpr)
    backend.resize(rect.width, rect.height, dpr)
    if (!motion) drawStatic()
  }

  function fallbackTo2D(reason: string) {
    if (disposed) return
    console.error(`[landing-scene] Falling back to Canvas 2D. Reason: ${reason}`)
    clearTimeout(restoreTimer)
    backend?.dispose()
    backend = null
    const next = createCanvas2DBackend(
      mountCanvas(),
      backendOptions(Math.min(options.density, FALLBACK_MAX_DENSITY)),
    )
    if (!next) {
      console.error('[landing-scene] No rendering backend is available; the scene will be empty.')
      canvas?.remove()
      canvas = null
      return
    }
    backend = next
    applySize()
  }

  // Initial backend selection.
  if (!options.forceCanvas2D) {
    backend = createWebGLBackend(mountCanvas(), backendOptions(options.density))
  } else {
    log('forced Canvas 2D renderer')
  }
  if (!backend)
    fallbackTo2D(options.forceCanvas2D ? 'forced via ?renderer=2d' : 'WebGL unavailable')

  function emitStats(now: number) {
    if (!options.onStats || !backend) return
    const elapsed = now - statWindowStart
    if (statWindowStart === 0) {
      statWindowStart = now
      return
    }
    if (elapsed < STATS_INTERVAL_MS) return
    options.onStats({
      backend: backend.kind,
      fps: (statFrames * 1000) / elapsed,
      frameMs: statDrawMs / Math.max(1, statFrames),
      stepMs: statStepMs / Math.max(1, statFrames),
      particles: backend.particleCount,
      agent: state.agentPoint(),
    })
    statWindowStart = now
    statFrames = 0
    statDrawMs = 0
    statStepMs = 0
  }

  function tick(now: number) {
    if (!running || disposed) return
    if (backend) {
      const t0 = performance.now()
      const dt = state.update(now)
      backend.draw(state, dt)
      statDrawMs += performance.now() - t0
      statStepMs += backend.lastStepMs
      statFrames += 1
      tickCount += 1
      if (tickCount === 1) log('requestAnimationFrame loop is running')
      if (!loggedAssembled && state.assemble >= 1) {
        loggedAssembled = true
        log('entrance finished', { frames: tickCount })
      }
      emitStats(now)
    }
    frame = requestAnimationFrame(tick)
  }

  return {
    get backend() {
      return backend ? backend.kind : 'none'
    },
    setPointer(point) {
      state.pointer = point
    },
    setHazardHover(hovered) {
      state.hazardHover = hovered
    },
    resize: applySize,
    start() {
      if (disposed || running || !backend) return
      if (!motion) {
        drawStatic()
        return
      }
      running = true
      state.resume()
      frame = requestAnimationFrame(tick)
    },
    stop() {
      running = false
      cancelAnimationFrame(frame)
    },
    dispose() {
      if (disposed) return
      disposed = true
      running = false
      cancelAnimationFrame(frame)
      clearTimeout(restoreTimer)
      backend?.dispose()
      backend = null
      canvas?.remove()
      canvas = null
    },
  }
}
