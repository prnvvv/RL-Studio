import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createSceneRenderer } from './sceneRenderer'

// A permissive Canvas 2D stand-in: any method is a no-op, gradients are objects.
function fake2dContext(): CanvasRenderingContext2D {
  const gradient = { addColorStop: vi.fn() }
  return new Proxy({} as Record<string, unknown>, {
    get: (target, prop: string) => {
      if (prop === 'createRadialGradient') return () => gradient
      if (prop in target) return target[prop]
      return vi.fn()
    },
    set: (target, prop: string, value) => {
      target[prop] = value
      return true
    },
  }) as unknown as CanvasRenderingContext2D
}

const OPTIONS = { density: 0.1, maxDpr: 1, reducedMotion: true, touch: false }

describe('createSceneRenderer fallback', () => {
  let host: HTMLDivElement
  let errorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    host = document.createElement('div')
    document.body.appendChild(host)
    vi.spyOn(host, 'getBoundingClientRect').mockReturnValue({
      width: 600,
      height: 400,
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 600,
      bottom: 400,
      toJSON: () => ({}),
    })
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
    host.remove()
  })

  it('logs a clear error and renders with Canvas 2D when WebGL is unavailable', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(((type: string) =>
      type === '2d' ? fake2dContext() : null) as never)

    const renderer = createSceneRenderer(host, OPTIONS)
    renderer.resize()
    renderer.start()

    expect(renderer.backend).toBe('canvas2d')
    expect(host.querySelectorAll('canvas')).toHaveLength(1)
    const messages = errorSpy.mock.calls.map((call: unknown[]) => String(call[0]))
    expect(messages.some((m: string) => m.includes('WebGL is unavailable'))).toBe(true)
    expect(messages.some((m: string) => m.includes('Falling back to Canvas 2D'))).toBe(true)

    renderer.dispose()
    expect(host.querySelectorAll('canvas')).toHaveLength(0)
  })

  it('can be forced onto the Canvas 2D renderer', () => {
    const getContext = vi
      .spyOn(HTMLCanvasElement.prototype, 'getContext')
      .mockImplementation(((type: string) => (type === '2d' ? fake2dContext() : null)) as never)

    const renderer = createSceneRenderer(host, { ...OPTIONS, forceCanvas2D: true })
    expect(renderer.backend).toBe('canvas2d')
    expect(getContext.mock.calls.some(([type]) => type === 'webgl')).toBe(false)
    renderer.dispose()
  })

  it('reports "none" and an explicit error when no backend can be created', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation((() => null) as never)

    const renderer = createSceneRenderer(host, OPTIONS)
    expect(renderer.backend).toBe('none')
    expect(
      errorSpy.mock.calls.some((call: unknown[]) =>
        String(call[0]).includes('No rendering backend'),
      ),
    ).toBe(true)
    // Lifecycle calls stay safe without a backend.
    renderer.resize()
    renderer.start()
    renderer.stop()
    renderer.dispose()
  })

  it('draws on the fallback when animated, and tears down cleanly', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(((type: string) =>
      type === '2d' ? fake2dContext() : null) as never)
    const frames: FrameRequestCallback[] = []
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => frames.push(cb))
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})

    const onStats = vi.fn()
    const renderer = createSceneRenderer(host, {
      ...OPTIONS,
      density: 0.02,
      reducedMotion: false,
      onStats,
    })
    renderer.resize()
    renderer.start()
    for (let i = 0; i < 60 && frames.length > 0; i += 1) frames.shift()?.(1000 + i * 16)

    expect(onStats).toHaveBeenCalled()
    expect(onStats.mock.calls[0][0].backend).toBe('canvas2d')
    renderer.dispose()
    expect(host.querySelectorAll('canvas')).toHaveLength(0)
  })
})
