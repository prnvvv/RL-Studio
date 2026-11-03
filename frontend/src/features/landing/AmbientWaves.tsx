import { useEffect, useRef } from 'react'
import { createField, particleCount, place } from './ambientField'

/** Frames per second. The motion is slow, so 30 is plenty and keeps the cost negligible. */
const FRAME_MS = 1000 / 30

/**
 * Faint particles drifting in waves in the corners of the first screen. A small 2D canvas that
 * lives behind all content (z-index and pointer-events are set in the stylesheet). It pauses when
 * it is off screen or the tab is hidden, and under prefers-reduced-motion it draws a single still
 * frame. It shares nothing with the sandbox particle scene.
 */
export function AmbientWaves() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext('2d')
    if (!canvas || !context) return // no canvas support (jsdom): the page is simply without it

    const reduced = () =>
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let width = 0
    let height = 0
    let field = createField(70)
    let frame = 0
    let last = 0
    let origin = performance.now()
    let onScreen = true

    const draw = (now: number) => {
      const t = (now - origin) / 1000
      context.clearRect(0, 0, width, height)
      context.fillStyle = '#ffffff'
      for (const particle of field.particles) {
        const placed = place(particle, field.waves, t, width, height)
        if (!placed) continue
        context.globalAlpha = placed.alpha
        context.beginPath()
        context.arc(placed.x, placed.y, placed.radius, 0, Math.PI * 2)
        context.fill()
      }
      context.globalAlpha = 1
    }

    const tick = (now: number) => {
      frame = requestAnimationFrame(tick)
      if (now - last < FRAME_MS) return
      last = now
      draw(now)
    }

    const stop = () => {
      cancelAnimationFrame(frame)
      frame = 0
    }
    const start = () => {
      if (frame !== 0 || reduced() || !onScreen || document.hidden) return
      last = 0
      frame = requestAnimationFrame(tick)
    }

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) return
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      width = rect.width
      height = rect.height
      canvas.width = Math.round(width * ratio)
      canvas.height = Math.round(height * ratio)
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
      field = createField(particleCount(width, height))
      draw(performance.now())
    }

    resize()
    const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize)
    resizeObserver?.observe(canvas)

    const visibility =
      typeof IntersectionObserver === 'undefined'
        ? null
        : new IntersectionObserver((entries) => {
            onScreen = entries.some((entry) => entry.isIntersecting)
            if (onScreen) start()
            else stop()
          })
    visibility?.observe(canvas)

    const onVisibility = () => (document.hidden ? stop() : start())
    document.addEventListener('visibilitychange', onVisibility)

    // Follow a change of the reduced-motion preference while the page is open.
    const query =
      typeof window.matchMedia === 'function'
        ? window.matchMedia('(prefers-reduced-motion: reduce)')
        : null
    const onMotion = () => {
      if (reduced()) {
        stop()
        origin = performance.now()
        draw(origin)
      } else {
        start()
      }
    }
    query?.addEventListener?.('change', onMotion)

    start()

    return () => {
      stop()
      resizeObserver?.disconnect()
      visibility?.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
      query?.removeEventListener?.('change', onMotion)
    }
  }, [])

  return <canvas ref={canvasRef} className="ls-ambient" aria-hidden="true" />
}
