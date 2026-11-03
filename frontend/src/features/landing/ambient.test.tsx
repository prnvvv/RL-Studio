import { render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AmbientWaves } from './AmbientWaves'
import {
  MAX_ALPHA,
  MIN_ALPHA,
  cornerWeight,
  createField,
  particleCount,
  place,
} from './ambientField'

describe('ambient particle field', () => {
  it('lays out the same sky for the same seed, and a different one for another', () => {
    expect(createField(120, 7)).toEqual(createField(120, 7))
    expect(createField(120, 7).particles).not.toEqual(createField(120, 8).particles)
    expect(createField(120).particles).toHaveLength(120)
  })

  it('keeps every particle small and within the intended opacity range', () => {
    for (const particle of createField(400).particles) {
      expect(particle.alpha).toBeGreaterThanOrEqual(MIN_ALPHA)
      expect(particle.alpha).toBeLessThanOrEqual(MAX_ALPHA)
      expect(particle.radius).toBeGreaterThanOrEqual(0.6)
      expect(particle.radius).toBeLessThanOrEqual(1.8)
    }
    expect(MIN_ALPHA).toBe(0.05)
    expect(MAX_ALPHA).toBeLessThanOrEqual(0.15)
  })

  it('gathers in the corners, strongest at the bottom-left, and leaves the middle empty', () => {
    expect(cornerWeight(0.02, 0.98)).toBeGreaterThan(0.9)
    expect(cornerWeight(0.02, 0.98)).toBeGreaterThan(cornerWeight(0.98, 0.02))
    expect(cornerWeight(0.98, 0.98)).toBeGreaterThan(cornerWeight(0.98, 0.02))
    // The middle, where the hero sits, gets a small fraction of the corner's weight (the stylesheet's
    // corner mask then blanks it completely).
    expect(cornerWeight(0.5, 0.45)).toBeLessThan(0.1)
    expect(cornerWeight(0.5, 0.45)).toBeLessThan(cornerWeight(0.02, 0.98) / 10)
    for (const [x, y] of [
      [0, 0],
      [1, 1],
      [0.3, 0.7],
      [0.5, 0.5],
      [1, 0],
    ]) {
      const weight = cornerWeight(x, y)
      expect(weight).toBeGreaterThanOrEqual(0)
      expect(weight).toBeLessThanOrEqual(1)
    }
  })

  it('uses fewer particles on a phone than on a desktop, within fixed limits', () => {
    const phone = particleCount(390, 844)
    const desktop = particleCount(1440, 900)
    expect(phone).toBeLessThan(desktop)
    expect(particleCount(10, 10)).toBe(180)
    expect(particleCount(8000, 8000)).toBe(700)
  })

  it('places particles inside the box, never brighter than their own opacity, and moves them over time', () => {
    const { particles, waves } = createField(300)
    let drawn = 0
    let moved = 0
    for (const particle of particles) {
      const early = place(particle, waves, 0, 1000, 600)
      const later = place(particle, waves, 40, 1000, 600)
      for (const placed of [early, later]) {
        if (!placed) continue
        drawn += 1
        expect(placed.x).toBeGreaterThanOrEqual(0)
        expect(placed.x).toBeLessThanOrEqual(1000)
        expect(placed.alpha).toBeGreaterThan(0)
        expect(placed.alpha).toBeLessThanOrEqual(particle.alpha + 1e-9)
      }
      if (early && later && (early.x !== later.x || early.y !== later.y)) moved += 1
    }
    expect(drawn).toBeGreaterThan(0)
    expect(moved).toBeGreaterThan(0) // the formation drifts
  })

  it('is a pure function of time: the same moment always gives the same picture', () => {
    const { particles, waves } = createField(50)
    expect(place(particles[3], waves, 12.5, 800, 500)).toEqual(
      place(particles[3], waves, 12.5, 800, 500),
    )
  })
})

describe('AmbientWaves', () => {
  const arc = vi.fn()
  const fakeContext = {
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    arc,
    fill: vi.fn(),
    setTransform: vi.fn(),
    fillStyle: '',
    globalAlpha: 1,
  }
  let raf: ReturnType<typeof vi.fn>

  const stubMotion = (reduced: boolean) =>
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation(() => ({
        matches: reduced,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )

  beforeEach(() => {
    arc.mockClear()
    raf = vi.fn().mockReturnValue(1)
    vi.stubGlobal('requestAnimationFrame', raf)
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      fakeContext as unknown as CanvasRenderingContext2D,
    )
    vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({
      width: 800,
      height: 600,
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 800,
      bottom: 600,
      toJSON: () => ({}),
    })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renders a decorative canvas that no assistive technology or pointer can reach', () => {
    stubMotion(false)
    const { container } = render(<AmbientWaves />)
    const canvas = container.querySelector('canvas')!
    expect(canvas).toHaveClass('ls-ambient')
    expect(canvas).toHaveAttribute('aria-hidden', 'true')
  })

  it('animates under normal motion', () => {
    stubMotion(false)
    render(<AmbientWaves />)
    expect(arc).toHaveBeenCalled() // the first frame is drawn at once
    expect(raf).toHaveBeenCalled() // and the loop keeps running
  })

  it('draws one still frame and no animation loop under prefers-reduced-motion', () => {
    stubMotion(true)
    render(<AmbientWaves />)
    expect(arc).toHaveBeenCalled()
    expect(raf).not.toHaveBeenCalled()
  })

  it('stops its loop when it is removed', () => {
    stubMotion(false)
    const cancel = vi.fn()
    vi.stubGlobal('cancelAnimationFrame', cancel)
    const { unmount } = render(<AmbientWaves />)
    unmount()
    expect(cancel).toHaveBeenCalled()
  })

  it('does nothing, without throwing, when the browser gives no 2D canvas', () => {
    stubMotion(false)
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
    expect(() => render(<AmbientWaves />)).not.toThrow()
    expect(raf).not.toHaveBeenCalled()
  })
})
