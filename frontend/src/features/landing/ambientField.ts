/**
 * The ambient background: tiny, faint particles drifting along slow waves, gathered in the outer
 * corners of the first screen. Pure functions only (no DOM), so the layout is deterministic and
 * testable. Nothing here is data; it is atmosphere.
 */

/** Opacity of a particle at full density. The effect is meant to be seen only on a closer look. */
export const MIN_ALPHA = 0.05
export const MAX_ALPHA = 0.12

export interface Particle {
  /** Position along its wave, 0..1 (wraps). */
  u: number
  /** Distance from the wave's centre line, as a fraction of the height. */
  v: number
  /** Which wave this particle belongs to. */
  band: number
  radius: number
  alpha: number
  /** Own drift speed, so neighbours slowly slide past each other. */
  drift: number
}

export interface Wave {
  /** Centre line height as a fraction of the height. */
  base: number
  amplitude: number
  /** Waves across the width. */
  frequency: number
  phase: number
  /** Radians per second. */
  speed: number
}

export interface Field {
  particles: Particle[]
  waves: Wave[]
}

/** Small seeded generator: the same seed always lays out the same sky. */
function mulberry32(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const WAVES: Wave[] = [
  // Long, gently curving bands. The low ones gather in the bottom-left and bottom-right corners.
  { base: 0.9, amplitude: 0.09, frequency: 0.9, phase: 0.4, speed: 0.07 },
  { base: 0.8, amplitude: 0.1, frequency: 0.7, phase: 2.1, speed: -0.05 },
  { base: 0.7, amplitude: 0.08, frequency: 1.1, phase: 4.0, speed: 0.06 },
  { base: 0.97, amplitude: 0.05, frequency: 1.4, phase: 1.2, speed: -0.08 },
  { base: 0.85, amplitude: 0.07, frequency: 1.2, phase: 5.6, speed: 0.05 },
  { base: 0.62, amplitude: 0.07, frequency: 0.8, phase: 0.9, speed: -0.04 },
  // High bands for the upper corners.
  { base: 0.12, amplitude: 0.06, frequency: 1.0, phase: 3.0, speed: 0.05 },
  { base: 0.22, amplitude: 0.07, frequency: 0.8, phase: 5.2, speed: -0.06 },
]

const clamp01 = (value: number) => Math.min(1, Math.max(0, value))

/**
 * How much of the effect shows at a point (both coordinates 0..1): strongest in the bottom-left
 * corner, softer in the other corners and nearly nothing in the middle, where the hero is.
 */
export function cornerWeight(nx: number, ny: number): number {
  const bottomLeft = Math.exp(-((nx / 0.42) ** 2 + ((1 - ny) / 0.5) ** 2))
  const bottomRight = 0.5 * Math.exp(-(((1 - nx) / 0.3) ** 2 + ((1 - ny) / 0.4) ** 2))
  const topLeft = 0.4 * Math.exp(-((nx / 0.28) ** 2 + (ny / 0.3) ** 2))
  const topRight = 0.3 * Math.exp(-(((1 - nx) / 0.25) ** 2 + (ny / 0.28) ** 2))
  return clamp01(bottomLeft + bottomRight + topLeft + topRight)
}

/** How many particles suit an area: sparse on phones, never heavy on large screens. */
export function particleCount(width: number, height: number): number {
  return Math.round(Math.min(700, Math.max(180, (width * height) / 1900)))
}

export function createField(count: number, seed = 7): Field {
  const random = mulberry32(seed)
  const gaussian = () => (random() + random() + random() - 1.5) / 1.5 // roughly -1..1, bell-shaped
  const particles: Particle[] = Array.from({ length: count }, () => {
    const band = Math.floor(random() * WAVES.length)
    // Many tiny particles and a few larger ones.
    const radius = 0.6 + random() ** 3 * 1.2
    return {
      u: random(),
      v: gaussian() * 0.018,
      band,
      radius,
      alpha: MIN_ALPHA + random() * (MAX_ALPHA - MIN_ALPHA),
      drift: (0.0018 + random() * 0.0035) * (random() < 0.5 ? -1 : 1),
    }
  })
  return { particles, waves: WAVES }
}

export interface Placed {
  x: number
  y: number
  radius: number
  alpha: number
}

/**
 * Where a particle is at time `t` (seconds) in a box of the given size, and how visible it is
 * there. Returns null when the point is too far from the corners to be worth drawing.
 */
export function place(
  particle: Particle,
  waves: Wave[],
  t: number,
  width: number,
  height: number,
): Placed | null {
  const wave = waves[particle.band]
  // Slow drift along the wave; wrap so the formation never runs out.
  const u = (((particle.u + particle.drift * t) % 1) + 1) % 1
  const x = u * width
  const crest =
    Math.sin(u * Math.PI * 2 * wave.frequency + wave.phase + t * wave.speed) +
    0.35 *
      Math.sin(u * Math.PI * 2 * wave.frequency * 2.3 + wave.phase * 1.7 - t * wave.speed * 0.6)
  const y = (wave.base + wave.amplitude * crest + particle.v) * height
  const weight = cornerWeight(x / width, y / height)
  if (weight < 0.06) return null
  // Fade at the seam where a particle wraps from one edge to the other.
  const seam = Math.min(1, u / 0.04, (1 - u) / 0.04)
  // The corner weight decides where particles show at all; within a corner each keeps most of its
  // own opacity, so the formation reads as soft grain rather than fading to nothing.
  return { x, y, radius: particle.radius, alpha: particle.alpha * (0.5 + 0.5 * weight) * seam }
}
