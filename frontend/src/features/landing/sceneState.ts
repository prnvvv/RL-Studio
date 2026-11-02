// Renderer-independent animation state for the landing scene. Both the WebGL
// and the Canvas 2D backends read this, so entrance, hover easing, the agent
// loop and the sprite list behave identically whichever one is active.

import { getSceneLayout, type Point, type SceneLayout } from './sceneGeometry'

export const ASSEMBLE_SECONDS = 1.5
const AGENT_LOOP_SECONDS = 13
const RIPPLE_SECONDS = 4.5
const AGENT_HOVER_RADIUS = 0.06
const MAX_DT = 0.05

export type AddSprite = (p: Point, size: number, alpha: number) => void

export interface StateOptions {
  reducedMotion: boolean
  touch: boolean
}

const ease = (current: number, target: number, rate: number, dt: number) =>
  current + (target - current) * (1 - Math.exp(-rate * dt))

export class SceneState {
  readonly layout: SceneLayout
  readonly options: StateOptions

  time = 0
  /** 0 = scattered, 1 = fully assembled. Driven by wall-clock time. */
  assemble: number
  mouse: Point = { x: 0.5, y: 0.5 }
  mouseAmt = 0
  hazardBoost = 0
  agentBoost = 0
  agentProgress = 0.02
  agentFade = 1
  rippleRadius = 0
  rippleAmt = 0

  /** Pointer in normalised scene coordinates, or null when outside. */
  pointer: Point | null = null
  hazardHover = false

  private assembleStart: number | null = null
  private lastNow: number | null = null

  constructor(options: StateOptions, layout: SceneLayout = getSceneLayout()) {
    this.options = options
    this.layout = layout
    this.assemble = options.reducedMotion ? 1 : 0
  }

  /** Call when the loop (re)starts so the first dt is not a huge gap. */
  resume(): void {
    this.lastNow = null
  }

  /** Reduced-motion / one-off frame: fully assembled, nothing moving. */
  setStatic(): void {
    this.assemble = 1
    this.mouseAmt = 0
    this.hazardBoost = 0
    this.agentBoost = 0
    this.time = 0
    this.agentProgress = 0.02
    this.agentFade = 1
    this.rippleAmt = 0
    this.rippleRadius = 0
  }

  agentPoint(): Point {
    const { path } = this.layout
    const index = Math.min(
      path.length - 1,
      Math.max(0, Math.round(this.agentProgress * (path.length - 1))),
    )
    return path[index]
  }

  /** Advances the state to `now` (ms) and returns the clamped dt in seconds. */
  update(now: number): number {
    const dt =
      this.lastNow === null ? 0 : Math.min(MAX_DT, Math.max(0, (now - this.lastNow) / 1000))
    this.lastNow = now
    this.time += dt

    // Entrance is wall-clock based so a slow first frame cannot stretch it.
    if (this.assemble < 1) {
      if (this.assembleStart === null) this.assembleStart = now
      this.assemble = Math.min(1, (now - this.assembleStart) / 1000 / ASSEMBLE_SECONDS)
    }

    const { pointer, options } = this
    if (pointer && !options.touch) {
      this.mouse = {
        x: ease(this.mouse.x, pointer.x, 14, dt),
        y: ease(this.mouse.y, pointer.y, 14, dt),
      }
      this.mouseAmt = ease(this.mouseAmt, 1, 10, dt)
    } else {
      // Slow release: displaced particles keep springing back after the cursor leaves.
      this.mouseAmt = ease(this.mouseAmt, 0, 3.2, dt)
    }
    this.hazardBoost = ease(
      this.hazardBoost,
      this.hazardHover ? 1 : 0,
      this.hazardHover ? 8 : 3,
      dt,
    )

    this.updateAgent(dt)

    if (options.touch) {
      const progress = (this.time % RIPPLE_SECONDS) / RIPPLE_SECONDS
      this.rippleRadius = progress * 0.7
      this.rippleAmt = (1 - progress) * 0.9
    }
    return dt
  }

  private updateAgent(dt: number): void {
    const loop = (this.time % AGENT_LOOP_SECONDS) / AGENT_LOOP_SECONDS
    this.agentProgress = loop
    this.agentFade = Math.min(1, loop / 0.06, (1 - loop) / 0.06)

    const { pointer, layout, options } = this
    let near = 0
    if (pointer && !options.touch) {
      const agent = this.agentPoint()
      const dx = (pointer.x - agent.x) * layout.aspect
      const dy = pointer.y - agent.y
      near = Math.hypot(dx, dy) < AGENT_HOVER_RADIUS * layout.aspect * 0.6 ? 1 : 0
    }
    this.agentBoost = ease(this.agentBoost, near, near ? 9 : 3, dt)
  }

  /** Static glows: waypoint nodes, goal pulse, agent with trail. */
  writeSprites(add: AddSprite): void {
    const { layout } = this
    const entrance = this.assemble
    const wobble = this.options.reducedMotion ? 0 : 1
    const { time, agentFade, agentProgress } = this

    layout.waypoints.forEach((p, i) => {
      const pulse = 0.85 + 0.15 * Math.sin(time * 1.4 + i) * wobble
      add(p, 26, 0.6 * pulse * entrance)
      add(p, 8, 1 * entrance)
    })
    add(layout.start, 12, 0.5 * entrance)

    const goalPulse = 0.7 + 0.3 * Math.sin(time * 1.8) * wobble
    add(layout.goal, 54, 0.32 * goalPulse * entrance)
    add(layout.goal, 14, 0.7 * entrance)

    const { path } = layout
    for (let k = 5; k >= 1; k -= 1) {
      const index = Math.max(0, Math.round((agentProgress - k * 0.012) * (path.length - 1)))
      add(path[index], 9 - k, 0.12 * (6 - k) * agentFade * entrance)
    }
    const agent = this.agentPoint()
    const haloBoost = 1 + this.agentBoost * 0.6
    add(agent, 58 * haloBoost, 0.34 * agentFade * entrance)
    add(agent, 20, 0.95 * agentFade * entrance)
    add(agent, 8, agentFade * entrance)
  }
}
