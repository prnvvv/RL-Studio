import { useEffect, useState } from 'react'
import type { StudioStore } from './studioStore'

const SAMPLE_MS = 500

interface Readout {
  /** Browser animation frames per second (how smoothly the viewport is drawing). */
  fps: number | null
  /** Simulation frames per second received from the backend. */
  stream: number | null
  rttMs: number | null
  /** Consecutive pings the server has not answered. */
  unanswered: number
}

const NO_REPLY_AFTER = 3

/**
 * Developer telemetry for the viewport corner. Every number is measured: FPS
 * from `requestAnimationFrame`, stream rate from received frames, latency from
 * WebSocket ping/pong round-trips. Unmeasured values show a dash.
 */
export function StreamOverlay({ store }: { store: StudioStore }) {
  const [readout, setReadout] = useState<Readout>({
    fps: null,
    stream: null,
    rttMs: null,
    unanswered: 0,
  })

  useEffect(() => {
    let animationFrames = 0
    let raf = 0
    const tick = () => {
      animationFrames += 1
      raf = requestAnimationFrame(tick)
    }
    if (typeof requestAnimationFrame === 'function') raf = requestAnimationFrame(tick)

    let lastTime = performance.now()
    let lastFrames = store.stream.frames
    const timer = window.setInterval(() => {
      const time = performance.now()
      const seconds = (time - lastTime) / 1000
      if (seconds <= 0) return
      const frames = store.stream.frames
      setReadout({
        fps:
          typeof requestAnimationFrame === 'function'
            ? Math.round(animationFrames / seconds)
            : null,
        stream: Math.round((frames - lastFrames) / seconds),
        rttMs: store.stream.rttMs,
        unanswered: store.stream.unanswered,
      })
      animationFrames = 0
      lastFrames = frames
      lastTime = time
    }, SAMPLE_MS)

    return () => {
      window.clearInterval(timer)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [store])

  const silent = readout.unanswered >= NO_REPLY_AFTER
  const show = (value: number | null, unit: string) => (value === null ? '—' : `${value}${unit}`)
  return (
    <div className="sim-telemetry" role="group" aria-label="Connection telemetry">
      <span>
        FPS <strong>{show(readout.fps, '')}</strong>
      </span>
      <span>
        Stream <strong>{show(readout.stream, '/s')}</strong>
      </span>
      <span
        title={
          silent
            ? 'The server has not answered the last pings. If this persists, restart the backend so it runs the current version.'
            : 'WebSocket round-trip time, measured with ping/pong'
        }
      >
        Latency{' '}
        <strong>
          {silent
            ? 'no reply'
            : show(readout.rttMs === null ? null : Math.round(readout.rttMs), ' ms')}
        </strong>
      </span>
    </div>
  )
}
