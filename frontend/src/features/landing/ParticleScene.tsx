import { useEffect, useMemo, useRef } from 'react'
import { createSceneRenderer, type SceneRenderer, type SceneStats } from './sceneRenderer'
import { getSceneLayout } from './sceneGeometry'

const TILT_DEGREES = 3.2
const DESKTOP_DENSITY = 0.45
const COMPACT_DENSITY = 0.3
const TOUCH_DENSITY = 0.2

// matchMedia is missing in some environments (e.g. jsdom): treat as "no match".
const mediaMatches = (query: string) =>
  typeof window.matchMedia === 'function' && window.matchMedia(query).matches

const pct = (value: number) => `${(value * 100).toFixed(2)}%`

/**
 * Opt-in developer flags, read from the query string. All are off by default:
 *   ?fps=1          frame-rate / timing readout over the scene
 *   ?debug=1        verbose console diagnostics (GL info, sizes, readback)
 *   ?renderer=2d    force the Canvas 2D fallback
 *   ?terrain=0      disable the Terrain-style block rise (plain repel instead)
 */
function readFlags() {
  const params = new URLSearchParams(window.location.search)
  return {
    fps: params.get('fps') === '1',
    debug: params.get('debug') === '1',
    forceCanvas2D: params.get('renderer') === '2d',
    terrain: params.get('terrain') !== '0',
  }
}

function formatStats(stats: SceneStats, debug: boolean): string {
  const base =
    `${stats.backend} · ${stats.particles.toLocaleString()} pts · ` +
    `${stats.fps.toFixed(0)} fps · draw ${stats.frameMs.toFixed(2)}ms · physics ${stats.stepMs.toFixed(2)}ms`
  return debug ? `${base} · agent ${stats.agent.x.toFixed(3)},${stats.agent.y.toFixed(3)}` : base
}

/**
 * Decorative isometric maze built entirely from particles. The whole subtree
 * is aria-hidden: the headline and CTAs carry the page meaning.
 */
export function ParticleScene() {
  const layout = useMemo(() => getSceneLayout(), [])
  const flags = useMemo(readFlags, [])
  const showStats = flags.fps || flags.debug
  const sceneRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const hostRef = useRef<HTMLDivElement>(null)
  const statsRef = useRef<HTMLDivElement>(null)
  const rendererRef = useRef<SceneRenderer | null>(null)

  useEffect(() => {
    const scene = sceneRef.current
    const stage = stageRef.current
    const host = hostRef.current
    if (!scene || !stage || !host) return

    const reducedMotion = mediaMatches('(prefers-reduced-motion: reduce)')
    const touch = mediaMatches('(hover: none), (pointer: coarse)')
    const compact = mediaMatches('(max-width: 1023px)')

    // The renderer creates its canvas inside this effect (StrictMode mounts
    // effects twice) and removes it again on cleanup, so releasing a GL
    // context can never hand a lost context to the next run.
    const renderer = createSceneRenderer(host, {
      density: touch ? TOUCH_DENSITY : compact ? COMPACT_DENSITY : DESKTOP_DENSITY,
      maxDpr: touch ? 1.5 : 2,
      reducedMotion,
      touch,
      debug: flags.debug,
      forceCanvas2D: flags.forceCanvas2D,
      terrain: flags.terrain,
      onStats: showStats
        ? (stats) => {
            if (statsRef.current) statsRef.current.textContent = formatStats(stats, flags.debug)
          }
        : undefined,
    })
    rendererRef.current = renderer
    renderer.resize()
    // eslint-disable-next-line no-console -- opt-in diagnostics behind ?debug=1
    if (flags.debug) console.info('[landing-scene] mounted', { reducedMotion, touch, compact })

    let onScreen = true
    let tabVisible = document.visibilityState !== 'hidden'
    const sync = () => (onScreen && tabVisible ? renderer.start() : renderer.stop())

    const cleanups: Array<() => void> = []
    if (typeof ResizeObserver !== 'undefined') {
      const resizeObserver = new ResizeObserver(() => renderer.resize())
      resizeObserver.observe(host)
      cleanups.push(() => resizeObserver.disconnect())
    } else {
      const onResize = () => renderer.resize()
      window.addEventListener('resize', onResize)
      cleanups.push(() => window.removeEventListener('resize', onResize))
    }
    if (typeof IntersectionObserver !== 'undefined') {
      const intersection = new IntersectionObserver(([entry]) => {
        onScreen = entry.isIntersecting
        sync()
      })
      intersection.observe(scene)
      cleanups.push(() => intersection.disconnect())
    }

    const onVisibility = () => {
      tabVisible = document.visibilityState !== 'hidden'
      sync()
    }
    document.addEventListener('visibilitychange', onVisibility)

    const resetPointer = () => {
      renderer.setPointer(null)
      stage.style.transform = ''
    }
    const onPointerMove = (event: PointerEvent) => {
      if (event.pointerType === 'touch') return
      const rect = host.getBoundingClientRect()
      const x = (event.clientX - rect.left) / rect.width
      const y = (event.clientY - rect.top) / rect.height
      const inside = x >= -0.05 && x <= 1.05 && y >= -0.05 && y <= 1.05
      renderer.setPointer(inside ? { x, y } : null)
      // Slow parallax tilt follows the cursor across the whole viewport.
      const vx = event.clientX / window.innerWidth - 0.5
      const vy = event.clientY / window.innerHeight - 0.5
      stage.style.transform = `perspective(1400px) rotateX(${(-vy * TILT_DEGREES).toFixed(2)}deg) rotateY(${(vx * TILT_DEGREES).toFixed(2)}deg)`
    }
    if (!touch && !reducedMotion) {
      window.addEventListener('pointermove', onPointerMove, { passive: true })
      document.documentElement.addEventListener('pointerleave', resetPointer)
    }

    sync()

    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('pointermove', onPointerMove)
      document.documentElement.removeEventListener('pointerleave', resetPointer)
      cleanups.forEach((dispose) => dispose())
      renderer.dispose()
      rendererRef.current = null
    }
  }, [flags, showStats])

  return (
    <div
      ref={sceneRef}
      className="ls-scene"
      aria-hidden="true"
      style={{
        aspectRatio: layout.aspect.toFixed(4),
        ['--ls-aspect' as string]: layout.aspect.toFixed(4),
      }}
    >
      <div ref={stageRef} className="ls-scene__stage">
        <div ref={hostRef} className="ls-scene__host" />

        {/* Markers use the same projected scene coordinates as the particle
            buffers, so they stay locked to the path at any size and tilt. */}
        <svg
          className="ls-marker ls-marker--goal"
          style={{ left: pct(layout.goal.x), top: pct(layout.goal.y) }}
          viewBox="0 0 24 28"
          width="22"
          height="26"
        >
          <path d="M5 26V2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M5 3h14l-3.2 4.4L19 12H5z" fill="currentColor" />
        </svg>
      </div>

      {showStats && (
        <div ref={statsRef} className="ls-scene__stats" data-testid="scene-stats">
          measuring…
        </div>
      )}
    </div>
  )
}
