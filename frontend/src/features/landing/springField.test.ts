import { describe, expect, it } from 'vitest'
import { SpringField } from './springField'

// Three particles on a row; stride 2 (x, y).
const base = new Float32Array([0.5, 0.5, 0.52, 0.5, 0.9, 0.9])
const ASPECT = 1.2
const STEP = 1 / 60

function run(field: SpringField, seconds: number, amount: number, mouse = { x: 0.5, y: 0.5 }) {
  let peak = 0
  for (let t = 0; t < seconds; t += STEP) {
    field.step(STEP, mouse, amount, ASPECT)
    peak = Math.max(peak, Math.abs(field.displacement[2]))
  }
  return peak
}

describe('SpringField', () => {
  it('pushes particles inside the cursor radius and leaves distant ones alone', () => {
    const field = new SpringField(base, 2, 3)
    run(field, 0.4, 1, { x: 0.49, y: 0.5 })
    expect(Math.hypot(field.displacement[0], field.displacement[1])).toBeGreaterThan(0)
    expect(field.displacement[4]).toBe(0)
    expect(field.displacement[5]).toBe(0)
  })

  it('pushes away from the cursor', () => {
    const field = new SpringField(base, 2, 3)
    // Cursor to the left of the second particle: it must move right (+x).
    run(field, 0.3, 1, { x: 0.45, y: 0.5 })
    expect(field.displacement[2]).toBeGreaterThan(0)
  })

  it('springs back to rest, with a small overshoot, after the cursor leaves', () => {
    const field = new SpringField(base, 2, 3)
    run(field, 0.5, 1)
    const displaced = field.displacement[2]
    expect(Math.abs(displaced)).toBeGreaterThan(0.01)

    let minSigned = Infinity
    for (let t = 0; t < 3; t += STEP) {
      field.step(STEP, { x: 0.5, y: 0.5 }, 0, ASPECT)
      minSigned = Math.min(minSigned, field.displacement[2] * Math.sign(displaced))
    }
    // Underdamped: it crosses the rest position at least once...
    expect(minSigned).toBeLessThan(0)
    // ...but the overshoot stays small relative to the push.
    expect(Math.abs(minSigned)).toBeLessThan(Math.abs(displaced) * 0.5)
    // ...and everything settles exactly at rest.
    expect(Array.from(field.displacement).every((v) => v === 0)).toBe(true)
  })

  it('stays bounded and finite for large frame gaps', () => {
    const field = new SpringField(base, 2, 3)
    for (let i = 0; i < 200; i += 1) field.step(0.5, { x: 0.5, y: 0.5 }, 1, ASPECT)
    expect(
      Array.from(field.displacement).every((v) => Number.isFinite(v) && Math.abs(v) < 0.5),
    ).toBe(true)
  })

  it('does no work while idle', () => {
    const field = new SpringField(base, 2, 3)
    expect(field.step(STEP, { x: 0.5, y: 0.5 }, 0, ASPECT)).toBe(false)
  })

  it('steps 30k particles well inside the 2ms budget', () => {
    const n = 30_000
    const big = new Float32Array(n * 2)
    for (let i = 0; i < n; i += 1) {
      big[i * 2] = Math.random()
      big[i * 2 + 1] = Math.random()
    }
    const field = new SpringField(big, 2, n)
    for (let i = 0; i < 30; i += 1) field.step(STEP, { x: 0.5, y: 0.5 }, 1, ASPECT) // warm up
    const t0 = performance.now()
    const frames = 60
    for (let i = 0; i < frames; i += 1) field.step(STEP, { x: 0.5, y: 0.5 }, 1, ASPECT)
    const perFrame = (performance.now() - t0) / frames
    // Generous bound for slow CI machines; real figure is reported in the dev FPS readout.
    expect(perFrame).toBeLessThan(2)
  })
})
