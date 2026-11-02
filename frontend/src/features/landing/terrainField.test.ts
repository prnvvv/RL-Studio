import { describe, expect, it } from 'vitest'
import { buildParticles, getSceneLayout } from './sceneGeometry'
import { TerrainField, terrainFalloff } from './terrainField'

const STEP = 1 / 60

function setup(density = 0.2) {
  const layout = getSceneLayout()
  const particles = buildParticles({ density })
  const field = new TerrainField(particles.blockIndex, particles.lift, layout)
  return { layout, particles, field }
}

function run(
  field: TerrainField,
  seconds: number,
  mouse: { x: number; y: number },
  amount: number,
) {
  for (let t = 0; t < seconds; t += STEP) field.step(STEP, mouse, amount)
}

/** Mean upward displacement (negative y) of particles on a given block's top. */
function riseOf(
  field: TerrainField,
  particles: ReturnType<typeof setup>['particles'],
  block: number,
) {
  let total = 0
  let n = 0
  for (let i = 0; i < particles.count; i += 1) {
    if (particles.blockIndex[i] === block && particles.lift[i] > 0.99) {
      total += -field.displacement[i * 2 + 1]
      n += 1
    }
  }
  return n > 0 ? total / n : 0
}

describe('terrainFalloff (ported from the Terrain figure)', () => {
  it('matches the published curve at its knots', () => {
    expect(terrainFalloff(0)).toBe(1)
    expect(terrainFalloff(0.417)).toBeCloseTo(0.3125, 4)
    expect(terrainFalloff(1)).toBeCloseTo(0.094, 3)
    expect(terrainFalloff(2.5)).toBe(0.094) // far field never reaches zero
  })

  it('decreases monotonically with distance', () => {
    let previous = Infinity
    for (let u = 0; u <= 1.5; u += 0.05) {
      const value = terrainFalloff(u)
      expect(value).toBeLessThanOrEqual(previous + 1e-12)
      previous = value
    }
  })
})

describe('TerrainField', () => {
  it('does nothing at rest', () => {
    const { field } = setup()
    expect(field.step(STEP, { x: 0.5, y: 0.5 }, 0)).toBe(false)
    expect(Array.from(field.displacement).every((v) => v === 0)).toBe(true)
  })

  it('raises blocks near the cursor more than far ones, and only upwards', () => {
    const { layout, particles, field } = setup()
    // Hover the centre of block 0 on the ground plane.
    const b0 = layout.blocks[0]
    const cursor = layout.toScene((b0.x0 + b0.x1) / 2, (b0.y0 + b0.y1) / 2)
    run(field, 1, cursor, 1)

    const far = layout.blocks.length - 1
    const nearRise = riseOf(field, particles, 0)
    const farRise = riseOf(field, particles, far)
    expect(nearRise).toBeGreaterThan(0.05)
    expect(nearRise).toBeGreaterThan(farRise * 2)
    // Every displacement is purely vertical and never pushes particles down.
    for (let i = 0; i < particles.count; i += 1) {
      expect(field.displacement[i * 2]).toBe(0)
      expect(field.displacement[i * 2 + 1]).toBeLessThanOrEqual(0)
    }
  })

  it('leaves dust, path and goal particles untouched', () => {
    const { layout, particles, field } = setup()
    run(field, 0.6, layout.toScene(3.5, 3.5), 1)
    for (let i = 0; i < particles.count; i += 1) {
      if (particles.blockIndex[i] < 0) expect(field.displacement[i * 2 + 1]).toBe(0)
    }
  })

  it('lifts a block top by more than its base (blocks stretch, not slide)', () => {
    const { layout, particles, field } = setup(0.45)
    const b = layout.blocks[10]
    run(field, 1, layout.toScene((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2), 1)
    let top = 0
    let base = 0
    let nTop = 0
    let nBase = 0
    for (let i = 0; i < particles.count; i += 1) {
      if (particles.blockIndex[i] !== 10) continue
      if (particles.lift[i] > 0.99) {
        top += -field.displacement[i * 2 + 1]
        nTop += 1
      } else if (particles.lift[i] < 0.15) {
        base += -field.displacement[i * 2 + 1]
        nBase += 1
      }
    }
    expect(nTop).toBeGreaterThan(0)
    expect(nBase).toBeGreaterThan(0)
    expect(top / nTop).toBeGreaterThan((base / nBase) * 3)
  })

  it('springs back to exactly the resting scene after the cursor leaves', () => {
    const { layout, field } = setup()
    run(field, 0.8, layout.toScene(3.5, 3.5), 1)
    expect(Array.from(field.displacement).some((v) => v !== 0)).toBe(true)
    run(field, 3, layout.toScene(3.5, 3.5), 0)
    expect(Array.from(field.displacement).every((v) => v === 0)).toBe(true)
    // ...and it is idle again.
    expect(field.step(STEP, { x: 0.5, y: 0.5 }, 0)).toBe(false)
  })

  it('stays finite for very large frame gaps', () => {
    const { layout, field } = setup()
    const cursor = layout.toScene(3.5, 3.5)
    for (let i = 0; i < 100; i += 1) field.step(0.5, cursor, 1)
    expect(Array.from(field.displacement).every((v) => Number.isFinite(v))).toBe(true)
  })

  it('costs well under the 2ms frame budget at the desktop particle count', () => {
    const { layout, field } = setup(0.45)
    const cursor = layout.toScene(3.5, 3.5)
    for (let i = 0; i < 30; i += 1) field.step(STEP, cursor, 1)
    const t0 = performance.now()
    for (let i = 0; i < 60; i += 1) field.step(STEP, cursor, 1)
    expect((performance.now() - t0) / 60).toBeLessThan(2)
  })
})
