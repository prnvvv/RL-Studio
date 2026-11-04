// Lightweight Canvas 2D fallback. Same layout, path, agent and hover physics
// as the WebGL backend, at a lower particle count. Used when WebGL cannot be
// created, fails to compile, draws nothing, or loses its context for good.

import type { BackendCallbacks, Logger, RenderBackend } from './backendTypes'
import { buildParticles, getSceneLayout, PARTICLE_STRIDE } from './sceneGeometry'
import type { SceneState } from './sceneState'
import { createDisplacementField } from './displacementField'

export interface Canvas2DBackendOptions {
  density: number
  terrain: boolean
  motion: boolean
  debug: boolean
  log: Logger
  callbacks: BackendCallbacks
}

const smoothstep = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

export function createCanvas2DBackend(
  canvas: HTMLCanvasElement,
  options: Canvas2DBackendOptions,
): RenderBackend | null {
  let ctx: CanvasRenderingContext2D | null
  try {
    ctx = canvas.getContext('2d', { alpha: true })
  } catch (error) {
    console.error('[landing-scene] Canvas 2D context creation threw:', error)
    return null
  }
  if (!ctx) {
    console.error('[landing-scene] Canvas 2D is unavailable (getContext returned null).')
    return null
  }
  const g = ctx

  const layout = getSceneLayout()
  const particles = buildParticles({ density: options.density })
  const { data, count } = particles
  const field = createDisplacementField(particles, options.terrain)

  let cssWidth = 1
  let cssHeight = 1
  let dpr = 1
  let sizeScale = 1

  return {
    kind: 'canvas2d',
    particleCount: count,
    lastStepMs: 0,

    resize(width, height, ratio) {
      cssWidth = Math.max(1, width)
      cssHeight = Math.max(1, height)
      dpr = ratio
      canvas.width = Math.round(cssWidth * dpr)
      canvas.height = Math.round(cssHeight * dpr)
      sizeScale = Math.min(1.35, Math.max(0.6, cssWidth / 780))
      if (options.debug) {
        options.log('2d resize', { css: [width, height], canvas: [canvas.width, canvas.height] })
      }
    },

    draw(state: SceneState, dt: number) {
      if (canvas.width === 0 || canvas.height === 0) return

      const t0 = performance.now()
      const moved = field.step(dt, state.mouse, state.mouseAmt, layout.aspect)
      this.lastStepMs = moved ? performance.now() - t0 : 0

      const light =
        typeof document !== 'undefined' &&
        document.documentElement.getAttribute('data-theme') === 'light'
      g.setTransform(dpr, 0, 0, dpr, 0, 0)
      g.clearRect(0, 0, cssWidth, cssHeight)
      g.globalCompositeOperation = light ? 'source-over' : 'lighter'
      g.fillStyle = light ? '#111111' : '#f0f0f0'

      const { assemble, time } = state
      const motion = options.motion ? 1 : 0
      const agent = state.agentPoint()
      const { aspect } = layout
      const disp = field.displacement
      const rippleOn = state.rippleAmt > 0.01

      for (let i = 0; i < count; i += 1) {
        const o = i * PARTICLE_STRIDE
        const seed = data[o + 6]
        const t = Math.min(1, Math.max(0, (assemble - seed * 0.4) / 0.6))
        if (t <= 0) continue
        const eased = 1 - (1 - t) ** 3

        let x = data[o + 2] + (data[o] - data[o + 2]) * eased
        let y = data[o + 3] + (data[o + 1] - data[o + 3]) * eased
        x += 0.0022 * motion * Math.sin(time * 0.7 + seed * 61)
        y += 0.0022 * motion * Math.cos(time * 0.55 + seed * 47)
        const dx = disp[i * 2]
        const dy = disp[i * 2 + 1]
        x += dx
        y += dy
        const push = Math.hypot(dx, dy)
        y -= Math.min(push * 0.45, 0.03)

        let bright = 1 + Math.min(push * (options.terrain ? 11 : 28), 2.2)
        if (rippleOn) {
          const rx = (x - 0.5) * aspect
          const ry = y - 0.5
          const rlen = Math.hypot(rx, ry)
          const rf =
            (1 - smoothstep(0, 0.07, Math.abs(rlen - state.rippleRadius))) * state.rippleAmt
          x += (rx / (rlen + 1e-4) / aspect) * rf * 0.035
          y += (ry / (rlen + 1e-4)) * rf * 0.035
          bright += rf
        }
        const ax = (x - agent.x) * aspect
        const ay = y - agent.y
        const agentDist = Math.hypot(ax, ay)
        if (agentDist < 0.09) {
          bright += (1 - smoothstep(0, 0.09, agentDist)) * (1.3 + state.agentBoost * 2.2)
        }
        if (state.hazardBoost > 0.01) {
          const hx = (x - layout.hazard.x) * aspect
          const hy = y - layout.hazard.y
          const hd = Math.hypot(hx, hy)
          if (hd < 0.1) bright += (1 - smoothstep(0, 0.1, hd)) * state.hazardBoost * 1.6
        }

        const ex = (data[o] - 0.5) * 2 * 0.92
        const ey = (data[o + 1] - 0.5) * 2
        const vignette = 1 - smoothstep(0.62, 1, Math.hypot(ex, ey))
        const twinkle = 0.88 + 0.12 * Math.sin(time * 1.3 * motion + seed * 90)
        const alpha = data[o + 5] * t * vignette * twinkle * Math.min(bright, 2.6)
        if (alpha < 0.02) continue

        const size = Math.max(1, data[o + 4] * sizeScale)
        g.globalAlpha = Math.min(1, alpha)
        g.fillRect(x * cssWidth - size / 2, y * cssHeight - size / 2, size, size)
      }

      g.globalAlpha = 1
      state.writeSprites((p, size, alpha) => {
        if (alpha <= 0.002) return
        const cx = p.x * cssWidth
        const cy = p.y * cssHeight
        const radius = (size * sizeScale) / 2
        const rgb = light ? '17,17,17' : '247,247,247'
        const gradient = g.createRadialGradient(cx, cy, 0, cx, cy, radius)
        gradient.addColorStop(0, `rgba(${rgb},${Math.min(1, alpha)})`)
        gradient.addColorStop(0.35, `rgba(${rgb},${Math.min(1, alpha * 0.28)})`)
        gradient.addColorStop(1, `rgba(${rgb},0)`)
        g.fillStyle = gradient
        g.beginPath()
        g.arc(cx, cy, radius, 0, Math.PI * 2)
        g.fill()
      })
      g.globalCompositeOperation = 'source-over'
    },

    dispose() {
      g.clearRect(0, 0, cssWidth, cssHeight)
    },
  }
}
