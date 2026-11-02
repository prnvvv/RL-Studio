import { describe, expect, it } from 'vitest'
import { buildParticles, getSceneLayout, PARTICLE_STRIDE } from './sceneGeometry'

describe('sceneGeometry', () => {
  it('lays the path out from the left of the scene to the upper right', () => {
    const { start, goal, hazard } = getSceneLayout()
    expect(start.x).toBeLessThan(0.3)
    expect(goal.x).toBeGreaterThan(0.6)
    expect(goal.y).toBeLessThan(start.y)
    expect(hazard.x).toBeGreaterThan(start.x)
    expect(hazard.x).toBeLessThan(goal.x)
  })

  it('keeps every path sample inside the normalised scene box', () => {
    const { path, aspect } = getSceneLayout()
    expect(aspect).toBeGreaterThan(0.8)
    for (const p of path) {
      expect(p.x).toBeGreaterThanOrEqual(0)
      expect(p.x).toBeLessThanOrEqual(1)
      expect(p.y).toBeGreaterThanOrEqual(0)
      expect(p.y).toBeLessThanOrEqual(1)
    }
  })

  it('never routes the path through a block footprint', () => {
    const { latticePath, blocks } = getSceneLayout()
    for (const p of latticePath) {
      const inside = blocks.some((b) => p.x > b.x0 && p.x < b.x1 && p.y > b.y0 && p.y < b.y1)
      expect(inside).toBe(false)
    }
  })

  it('is deterministic and scales particle count with density', () => {
    const a = buildParticles({ density: 0.45 })
    const b = buildParticles({ density: 0.45 })
    const sparse = buildParticles({ density: 0.2 })
    expect(a.data).toEqual(b.data)
    expect(a.data.length).toBe(a.count * PARTICLE_STRIDE)
    expect(a.count).toBeGreaterThan(20_000)
    expect(a.count).toBeLessThan(40_000)
    expect(sparse.count).toBeLessThan(a.count)
  })

  it('keeps the resting particle buffer byte-identical (hover work must be additive)', () => {
    const fnv = (data: Float32Array) => {
      let h = 2166136261
      for (const word of new Uint32Array(data.buffer)) h = Math.imul(h ^ word, 16777619) >>> 0
      return h
    }
    const desktop = buildParticles({ density: 0.45 })
    const touch = buildParticles({ density: 0.2 })
    expect([desktop.count, fnv(desktop.data)]).toEqual([25673, 1246743363])
    expect([touch.count, fnv(touch.data)]).toEqual([11684, 1436401555])
  })

  it('inverts toScene on the ground plane', () => {
    const { toScene, fromScene } = getSceneLayout()
    for (const [x, y] of [
      [0, 0],
      [3.5, 2],
      [7, 7],
      [6.2, 0.4],
    ]) {
      const back = fromScene(toScene(x, y).x, toScene(x, y).y)
      expect(back.x).toBeCloseTo(x, 6)
      expect(back.y).toBeCloseTo(y, 6)
    }
  })

  it('tags every particle with its block and height fraction', () => {
    const { count, blockIndex, lift } = buildParticles({ density: 0.2 })
    const { blocks } = getSceneLayout()
    expect(blockIndex).toHaveLength(count)
    expect(lift).toHaveLength(count)
    expect(blockIndex.some((b) => b === -1)).toBe(true) // dust, path, goal ring
    for (let i = 0; i < count; i += 1) {
      expect(blockIndex[i]).toBeGreaterThanOrEqual(-1)
      expect(blockIndex[i]).toBeLessThan(blocks.length)
      expect(lift[i]).toBeGreaterThanOrEqual(-1e-6)
      expect(lift[i]).toBeLessThanOrEqual(1 + 1e-6)
      if (blockIndex[i] < 0) expect(lift[i]).toBe(0)
    }
  })
})
