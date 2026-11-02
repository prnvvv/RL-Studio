import { describe, expect, it } from 'vitest'
import { SceneState } from './sceneState'

const ANIMATED = { reducedMotion: false, touch: false }

describe('SceneState', () => {
  it('assembles by wall-clock time even when frames are slow', () => {
    const state = new SceneState(ANIMATED)
    state.update(1000)
    expect(state.assemble).toBe(0)
    // Two slow 0.5s frames: dt is clamped, but the entrance must not stretch.
    state.update(1750)
    expect(state.assemble).toBeCloseTo(0.5, 1)
    state.update(2600)
    expect(state.assemble).toBe(1)
  })

  it('starts assembled and static under reduced motion', () => {
    const state = new SceneState({ reducedMotion: true, touch: false })
    expect(state.assemble).toBe(1)
    state.setStatic()
    expect(state.mouseAmt).toBe(0)
    expect(state.agentProgress).toBeCloseTo(0.02)
  })

  it('eases cursor influence in and releases it slowly', () => {
    const state = new SceneState(ANIMATED)
    state.pointer = { x: 0.4, y: 0.4 }
    for (let t = 0; t < 60; t += 1) state.update(t * 16)
    expect(state.mouseAmt).toBeGreaterThan(0.9)

    state.pointer = null
    state.update(61 * 16)
    expect(state.mouseAmt).toBeGreaterThan(0.5) // not an instant snap
    for (let t = 62; t < 300; t += 1) state.update(t * 16)
    expect(state.mouseAmt).toBeLessThan(0.01)
  })

  it('ignores the pointer on touch devices and runs the ripple instead', () => {
    const state = new SceneState({ reducedMotion: false, touch: true })
    state.pointer = { x: 0.5, y: 0.5 }
    for (let t = 0; t < 30; t += 1) state.update(t * 16)
    expect(state.mouseAmt).toBe(0)
    expect(state.rippleRadius).toBeGreaterThan(0)
    expect(state.rippleAmt).toBeGreaterThan(0)
  })

  it('intensifies hazard and agent hover and releases them', () => {
    const state = new SceneState(ANIMATED)
    state.hazardHover = true
    state.pointer = state.agentPoint()
    for (let t = 0; t < 40; t += 1) state.update(t * 16)
    expect(state.hazardBoost).toBeGreaterThan(0.9)
    expect(state.agentBoost).toBeGreaterThan(0.5)

    state.hazardHover = false
    state.pointer = null
    for (let t = 40; t < 400; t += 1) state.update(t * 16)
    expect(state.hazardBoost).toBeLessThan(0.05)
    expect(state.agentBoost).toBeLessThan(0.05)
  })

  it('moves the agent along the path and loops', () => {
    const state = new SceneState(ANIMATED)
    const start = state.agentPoint()
    for (let t = 0; t < 400; t += 1) state.update(t * 16) // ~6.4s of a 13s loop
    const mid = state.agentPoint()
    expect(Math.hypot(mid.x - start.x, mid.y - start.y)).toBeGreaterThan(0.1)
    for (let t = 400; t < 1000; t += 1) state.update(t * 16) // past one full loop
    expect(state.agentProgress).toBeLessThan(1)
  })

  it('emits sprites for waypoints, goal and agent, and none for the cursor', () => {
    const state = new SceneState(ANIMATED)
    state.assemble = 1
    const quiet: number[] = []
    state.writeSprites((p) => quiet.push(p.x))
    expect(quiet.length).toBeGreaterThan(10)

    // Hovering must not add any cursor sprite (the cursor ring was removed).
    state.mouseAmt = 1
    state.mouse = { x: 0.123, y: 0.456 }
    const hovered: number[] = []
    let atCursor = 0
    state.writeSprites((p) => {
      hovered.push(p.x)
      if (p.x === 0.123 && p.y === 0.456) atCursor += 1
    })
    expect(hovered.length).toBe(quiet.length)
    expect(atCursor).toBe(0)
  })
})
