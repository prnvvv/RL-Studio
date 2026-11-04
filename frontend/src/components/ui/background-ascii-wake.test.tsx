import { render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { WakeGlyph } from './background-ascii-wake'

function fakeContext() {
  return {
    setTransform: vi.fn(),
    clearRect: vi.fn(),
    fillText: vi.fn(),
    globalAlpha: 1,
    fillStyle: '',
    font: '',
    textAlign: '',
    textBaseline: '',
  }
}

describe('WakeGlyph', () => {
  let context: ReturnType<typeof fakeContext>

  beforeEach(() => {
    context = fakeContext()
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      context as unknown as CanvasRenderingContext2D,
    )
    vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({
      left: 0,
      top: 0,
      width: 360,
      height: 360,
      right: 360,
      bottom: 360,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn() }),
    )
    vi.stubGlobal('requestAnimationFrame', vi.fn().mockReturnValue(1))
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
  })
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('renders a decorative canvas that merges the given class', () => {
    const { container } = render(<WakeGlyph className="ls-wake" cellSize={18} />)
    const canvas = container.querySelector('canvas')
    expect(canvas).toHaveAttribute('aria-hidden', 'true')
    expect(canvas).toHaveClass('wake-glyph', 'ls-wake')
  })

  it('draws only dim glyphs: alpha never exceeds 0.6', () => {
    const alphas: number[] = []
    Object.defineProperty(context, 'globalAlpha', {
      set: (v: number) => alphas.push(v),
      get: () => 1,
    })
    const { container } = render(
      <div>
        <WakeGlyph cellSize={18} />
      </div>,
    )
    const host = container.firstElementChild as HTMLElement
    host.dispatchEvent(new MouseEvent('pointermove', { clientX: 20, clientY: 20, bubbles: true }))
    expect(alphas.every((a) => a <= 1)).toBe(true)
    expect(alphas.filter((a) => a !== 1).every((a) => a <= 0.6)).toBe(true)
  })

  it('tracks the pointer on the parent so the canvas can stay click-through', () => {
    const add = vi.spyOn(HTMLElement.prototype, 'addEventListener')
    const { container } = render(
      <div>
        <WakeGlyph />
      </div>,
    )
    const canvas = container.querySelector('canvas')
    const targets = add.mock.calls
      .map(([type], i) => (type === 'pointermove' ? add.mock.contexts[i] : null))
      .filter(Boolean)
    expect(targets).toContain(container.firstElementChild)
    expect(targets).not.toContain(canvas)
  })

  it('draws one still frame and ignores the pointer under reduced motion', () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn() }),
    )
    render(<WakeGlyph />)
    expect(requestAnimationFrame).not.toHaveBeenCalled()
    expect(context.clearRect).toHaveBeenCalled()
  })

  it('does nothing when 2D canvas is unavailable', () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    expect(() => render(<WakeGlyph />)).not.toThrow()
  })

  it('cancels its frame loop on unmount', () => {
    const { unmount } = render(<WakeGlyph />)
    unmount()
    expect(cancelAnimationFrame).toHaveBeenCalled()
  })
})
