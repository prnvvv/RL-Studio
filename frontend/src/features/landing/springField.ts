// Per-particle spring-damper displacement, simulated on the CPU in typed
// arrays. Particles inside the cursor radius are pushed outwards; a damped
// spring pulls every particle back to its rest position, so released
// particles overshoot slightly and settle (damping ratio ~0.5).

import type { Point } from './sceneGeometry'

const RADIUS = 0.13
const PUSH = 4.2 // acceleration scale; steady-state displacement = PUSH / STIFFNESS
const STIFFNESS = 70
const DAMPING = 8.5
const MAX_STEP = 1 / 30 // keeps the semi-implicit Euler integration stable
const REST_EPSILON = 1e-5

export class SpringField {
  /** Interleaved (x, y) displacement per particle, ready to upload as an attribute. */
  readonly displacement: Float32Array
  private readonly velocity: Float32Array
  private moving = false

  constructor(
    private readonly base: Float32Array,
    private readonly stride: number,
    readonly count: number,
  ) {
    this.displacement = new Float32Array(count * 2)
    this.velocity = new Float32Array(count * 2)
  }

  /** Returns true when the displacement buffer changed and needs re-uploading. */
  step(rawDt: number, mouse: Point, amount: number, aspect: number): boolean {
    const pushing = amount > 0.01
    if (!pushing && !this.moving) return false

    const dt = Math.min(rawDt, MAX_STEP)
    if (dt <= 0) return false

    const { base, stride, count, displacement: disp, velocity: vel } = this
    const radius2 = RADIUS * RADIUS
    let energy = 0

    for (let i = 0; i < count; i += 1) {
      const ix = i * 2
      const iy = ix + 1
      let dx = disp[ix]
      let dy = disp[iy]
      let ax = -STIFFNESS * dx - DAMPING * vel[ix]
      let ay = -STIFFNESS * dy - DAMPING * vel[iy]

      if (pushing) {
        // Distance uses the current (displaced) position so pushed particles
        // leave the field and then spring back in.
        const px = base[i * stride] + dx - mouse.x
        const py = base[i * stride + 1] + dy - mouse.y
        const cx = px * aspect
        const d2 = cx * cx + py * py
        if (d2 < radius2 && d2 > 1e-10) {
          const d = Math.sqrt(d2)
          const falloff = 1 - d / RADIUS
          const force = falloff * falloff * amount * PUSH
          ax += (cx / d / aspect) * force
          ay += (py / d) * force
        }
      }

      vel[ix] += ax * dt
      vel[iy] += ay * dt
      dx += vel[ix] * dt
      dy += vel[iy] * dt
      disp[ix] = dx
      disp[iy] = dy
      energy += Math.abs(dx) + Math.abs(dy) + Math.abs(vel[ix]) * 0.1 + Math.abs(vel[iy]) * 0.1
    }

    if (!pushing && energy < REST_EPSILON * count) {
      disp.fill(0)
      vel.fill(0)
      this.moving = false
    } else {
      this.moving = true
    }
    return true
  }
}
