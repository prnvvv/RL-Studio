import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act } from 'react'
import { renderHook } from '@testing-library/react'
import { usePlayback } from './usePlayback'

const ADVANCE_MS = 100 // narrow constant for timer math in tests

describe('usePlayback', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts at the beginning of the recorded window, paused', () => {
    const { result } = renderHook(() => usePlayback(10, 15, ADVANCE_MS))
    expect(result.current.timestep).toBe(10)
    expect(result.current.playing).toBe(false)
    expect(result.current.atStart).toBe(true)
    expect(result.current.atEnd).toBe(false)
  })

  it('advances one recorded timestep per interval while playing', () => {
    const { result } = renderHook(() => usePlayback(10, 15, ADVANCE_MS))
    act(() => result.current.play())
    expect(result.current.playing).toBe(true)
    expect(result.current.timestep).toBe(10)

    act(() => vi.advanceTimersByTime(ADVANCE_MS))
    expect(result.current.timestep).toBe(11)

    act(() => vi.advanceTimersByTime(ADVANCE_MS * 2))
    expect(result.current.timestep).toBe(13)
  })

  it('auto-pauses at the last recorded timestep instead of looping', () => {
    const { result } = renderHook(() => usePlayback(10, 13, ADVANCE_MS))
    act(() => result.current.play())
    // Walk the full recording and well past its end.
    act(() => vi.advanceTimersByTime(ADVANCE_MS * 20))
    expect(result.current.timestep).toBe(13)
    expect(result.current.atEnd).toBe(true)
    expect(result.current.playing).toBe(false)
    // Time passing without playing changes nothing.
    act(() => vi.advanceTimersByTime(ADVANCE_MS * 10))
    expect(result.current.timestep).toBe(13)
  })

  it('treats play at the end of the recording as a no-op', () => {
    const { result } = renderHook(() => usePlayback(10, 12, ADVANCE_MS))
    act(() => result.current.jumpToEnd())
    act(() => result.current.play())
    expect(result.current.playing).toBe(false)
    expect(result.current.timestep).toBe(12)
  })

  it('pauses and clamps on manual stepping', () => {
    const { result } = renderHook(() => usePlayback(10, 12, ADVANCE_MS))
    act(() => result.current.play())
    act(() => result.current.stepForward())
    expect(result.current.playing).toBe(false)
    expect(result.current.timestep).toBe(11)

    // Stepping never passes the recorded bounds.
    act(() => {
      result.current.stepForward()
      result.current.stepForward()
    })
    expect(result.current.timestep).toBe(12)
    act(() => {
      result.current.stepBack()
      result.current.stepBack()
      result.current.stepBack()
    })
    expect(result.current.timestep).toBe(10)
    expect(result.current.atStart).toBe(true)
  })

  it('jumps to the recorded bounds and pauses', () => {
    const { result } = renderHook(() => usePlayback(10, 15, ADVANCE_MS))
    act(() => result.current.play())
    act(() => result.current.jumpToEnd())
    expect(result.current.playing).toBe(false)
    expect(result.current.timestep).toBe(15)
    act(() => result.current.jumpToStart())
    expect(result.current.timestep).toBe(10)
    expect(result.current.atStart).toBe(true)
  })

  it('clamps scrubbing to the recorded window and pauses', () => {
    const { result } = renderHook(() => usePlayback(10, 15, ADVANCE_MS))
    act(() => result.current.play())
    act(() => result.current.goTo(999))
    expect(result.current.playing).toBe(false)
    expect(result.current.timestep).toBe(15)
    act(() => result.current.goTo(3))
    expect(result.current.timestep).toBe(10)
    act(() => result.current.goTo(13))
    expect(result.current.timestep).toBe(13)
  })

  it('resets to the new window when the recording changes', () => {
    const { result, rerender } = renderHook(({ min, max }) => usePlayback(min, max, ADVANCE_MS), {
      initialProps: { min: 10, max: 15 },
    })
    act(() => result.current.jumpToEnd())
    expect(result.current.timestep).toBe(15)

    // A different recording (partial, starting later) resets the cursor.
    rerender({ min: 796, max: 825 })
    expect(result.current.timestep).toBe(796)
    expect(result.current.playing).toBe(false)
    expect(result.current.atStart).toBe(true)
  })

  it('stops the advance timer on unmount', () => {
    const { result, unmount } = renderHook(() => usePlayback(10, 15, ADVANCE_MS))
    act(() => result.current.play())
    unmount()
    // If the interval leaked, advancing time would trigger a state update on
    // the unmounted hook — React would warn; assert time passes silently and
    // spy on console.error to be explicit.
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      act(() => vi.advanceTimersByTime(ADVANCE_MS * 5))
      expect(errorSpy).not.toHaveBeenCalled()
    } finally {
      errorSpy.mockRestore()
    }
  })
})
