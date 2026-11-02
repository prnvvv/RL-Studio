// "Terrain" hover: the maze blocks rise around the cursor and spring back.
//
// This is a port of the pointer behaviour of `Terrain` from
// @lucasmarkes/hairline (MIT, https://github.com/lucasmarkes/hairline), read
// from its published source (v0.5.1, src/figures/terrain.ts), re-expressed on
// this scene's blocks instead of its own 81 SVG pillars:
//   - the pointer is unprojected onto the ground plane,
//   - each pillar's target height is HMAX * falloff(distance / R), where the
//     falloff is 1 at the cursor, 0.3125 at 0.417R, 0.094 at R and stays at
//     0.094 beyond (so the whole terrain wakes slightly while hovering),
//   - each pillar follows its target on its own spring (k = 100, c = 18).
// The package itself is not a dependency: it draws opaque SVG plates of its
// own geometry, which cannot be composited over this particle scene.
//
// The result is written as a per-particle vertical displacement, so it flows
// through the same attribute/buffer as the repel field in both backends.

import type { DisplacementField } from './displacementField'
import type { Point, SceneLayout } from './sceneGeometry'

/** Radius of influence in lattice cells (Terrain: 3 of 9 cells; scaled to a 7-wide maze). */
const RADIUS = 2.33
/** Peak extra block height, in lattice units (blocks are 0.16 - 0.71 tall at rest). */
const RISE = 1.0
const STIFFNESS = 100
const DAMPING = 18
const SUBSTEP = 1 / 240
const MAX_DT = 0.05
const POS_EPS = 0.0005
const VEL_EPS = 0.005

/** Terrain's falloff curve, with `u = distance / radius`. */
export function terrainFalloff(u: number): number {
  if (u <= 0) return 1
  if (u <= 0.417) return 1 - (u / 0.417) * 0.6875
  if (u <= 1) return 0.3125 - ((u - 0.417) / 0.583) * 0.2185
  return 0.094
}

export class TerrainField implements DisplacementField {
  readonly displacement: Float32Array
  private readonly centers: Point[]
  private readonly rise: Float32Array
  private readonly velocity: Float32Array
  private moving = false

  constructor(
    private readonly blockIndex: Int16Array,
    private readonly lift: Float32Array,
    private readonly layout: SceneLayout,
  ) {
    this.displacement = new Float32Array(blockIndex.length * 2)
    this.centers = layout.blocks.map((b) => ({ x: (b.x0 + b.x1) / 2, y: (b.y0 + b.y1) / 2 }))
    this.rise = new Float32Array(layout.blocks.length)
    this.velocity = new Float32Array(layout.blocks.length)
  }

  /** Returns true when the displacement buffer changed and needs re-uploading. */
  step(dt: number, mouse: Point, amount: number): boolean {
    const active = amount > 0.01
    if (!active && !this.moving) return false
    if (dt <= 0) return false

    const ground = this.layout.fromScene(mouse.x, mouse.y)
    const { rise, velocity, centers } = this
    const clamped = Math.min(dt, MAX_DT)
    const steps = Math.max(1, Math.ceil(clamped / SUBSTEP))
    const h = clamped / steps
    let anyMoving = false

    for (let b = 0; b < rise.length; b += 1) {
      const target = active
        ? amount *
          RISE *
          terrainFalloff(Math.hypot(centers[b].x - ground.x, centers[b].y - ground.y) / RADIUS)
        : 0
      let x = rise[b]
      let v = velocity[b]
      for (let i = 0; i < steps; i += 1) {
        v += (-STIFFNESS * (x - target) - DAMPING * v) * h
        x += v * h
      }
      if (!active && Math.abs(x - target) < POS_EPS && Math.abs(v) < VEL_EPS) {
        x = 0
        v = 0
      } else {
        anyMoving = true
      }
      rise[b] = x
      velocity[b] = v
    }
    this.moving = anyMoving

    const { displacement: disp, blockIndex, lift } = this
    const { unitY } = this.layout
    for (let i = 0; i < blockIndex.length; i += 1) {
      const b = blockIndex[i]
      disp[i * 2 + 1] = b < 0 ? 0 : -lift[i] * rise[b] * unitY
    }
    return true
  }
}
