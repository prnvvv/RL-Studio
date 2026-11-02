import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Playback state machine over recorded timesteps.
 *
 * The playback cursor is always expressed in the recording's OWN timestep
 * units, so scrubbing matches the recorded data (which may start above zero
 * when the recording covers a later training window). Advancing never invents
 * positions: every accepted timestep must satisfy `min <= t <= max`, and the
 * last recorded step is reached only through explicit controls.
 *
 * Timers are bounded and cleaned up on unmount; playback auto-pauses at the
 * end instead of looping, so a viewer can never silently fabricate continued
 * activity after the recording stops.
 */
export interface PlaybackControls {
  /** Recorded timestep currently displayed. */
  timestep: number
  playing: boolean
  atStart: boolean
  atEnd: boolean
  /** Start (or resume) automatic advance. No-op at the end of the recording. */
  play: () => void
  pause: () => void
  /** Move one recorded timestep forward/back and pause automatic advance. */
  stepForward: () => void
  stepBack: () => void
  jumpToStart: () => void
  jumpToEnd: () => void
  /** Scrub to an arbitrary recorded timestep; clamped, pauses playback. */
  goTo: (timestep: number) => void
}

const DEFAULT_ADVANCE_MS = 220

export function usePlayback(
  min: number,
  max: number,
  advanceMs = DEFAULT_ADVANCE_MS,
): PlaybackControls {
  const [timestep, setTimestep] = useState(min)
  const [playing, setPlaying] = useState(false)
  // Mirror of `timestep` so event handlers can guard the end of the recording
  // synchronously without reading state inside a state updater.
  const timestepRef = useRef(min)
  timestepRef.current = timestep
  // Keep the interval timer in a ref so effects can stop the exact timer.
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Reset when the recording window changes (e.g. a different replay loaded).
  useEffect(() => {
    setTimestep(min)
    setPlaying(false)
  }, [min, max])

  const stopTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!playing) {
      stopTimer()
      return
    }
    if (timestep >= max) {
      // Reached the end: auto-pause instead of looping or fabricating more.
      setPlaying(false)
      return
    }
    timerRef.current = setInterval(() => {
      setTimestep((current) => {
        if (current >= max) return current
        return Math.min(current + 1, max)
      })
    }, advanceMs)
    // stopTimer is a stable useCallback; returning it also covers unmount.
    return stopTimer
  }, [playing, timestep, max, advanceMs, stopTimer])

  useEffect(() => stopTimer, [stopTimer])

  const pause = useCallback(() => setPlaying(false), [])
  const play = useCallback(() => {
    if (timestepRef.current >= max) return
    setPlaying(true)
  }, [max])

  const stepForward = useCallback(() => {
    setPlaying(false)
    setTimestep((current) => Math.min(current + 1, max))
  }, [max])

  const stepBack = useCallback(() => {
    setPlaying(false)
    setTimestep((current) => Math.max(current - 1, min))
  }, [min])

  const jumpToStart = useCallback(() => {
    setPlaying(false)
    setTimestep(min)
  }, [min])

  const jumpToEnd = useCallback(() => {
    setPlaying(false)
    setTimestep(max)
  }, [max])

  const goTo = useCallback(
    (requested: number) => {
      setPlaying(false)
      setTimestep(Math.min(Math.max(requested, min), max))
    },
    [min, max],
  )

  return {
    timestep,
    playing,
    atStart: timestep <= min,
    atEnd: timestep >= max,
    play,
    pause,
    stepForward,
    stepBack,
    jumpToStart,
    jumpToEnd,
    goTo,
  }
}
