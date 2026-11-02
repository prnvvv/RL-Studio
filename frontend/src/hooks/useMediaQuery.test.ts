import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useMediaQuery } from './useMediaQuery'

/** Minimal controllable fake so tests can fire a 'change' event deterministically. */
function fakeMediaQueryList(initialMatches: boolean) {
  let matches = initialMatches
  const listeners = new Set<(event: MediaQueryListEvent) => void>()

  const list = {
    get matches() {
      return matches
    },
    media: '',
    addEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.add(listener)
    },
    removeEventListener: (_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.delete(listener)
    },
  }

  function setMatches(next: boolean) {
    matches = next
    listeners.forEach((listener) => listener({ matches: next } as MediaQueryListEvent))
  }

  return { list, setMatches }
}

describe('useMediaQuery', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reports the query result at mount', () => {
    const { list } = fakeMediaQueryList(true)
    vi.stubGlobal('matchMedia', () => list)

    const { result } = renderHook(() => useMediaQuery('(max-width: 960px)'))

    expect(result.current).toBe(true)
  })

  it('updates when the media query result changes', () => {
    const { list, setMatches } = fakeMediaQueryList(false)
    vi.stubGlobal('matchMedia', () => list)

    const { result } = renderHook(() => useMediaQuery('(max-width: 960px)'))
    expect(result.current).toBe(false)

    act(() => setMatches(true))
    expect(result.current).toBe(true)
  })
})
