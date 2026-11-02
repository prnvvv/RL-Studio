// Pure, seeded geometry for the landing-page particle scene. Nothing here
// touches the DOM or WebGL, so it is deterministic and unit-testable.
//
// World space is a square lattice: blocks sit between corridor centre lines at
// integer coordinates. `project` maps the lattice to an isometric screen where
// +x runs up-right and +y runs down-right, so the start (left) and goal
// (upper right) of the path read naturally.

export interface Point {
  x: number
  y: number
}

export interface SceneBlock {
  x0: number
  x1: number
  y0: number
  y1: number
  height: number
}

/** Interleaved layout of the particle buffer, in floats. */
export const PARTICLE_STRIDE = 7 // baseX, baseY, scatterX, scatterY, size, alpha, seed

export const GRID_SIZE = 7
const CORRIDOR_WIDTH = 0.42
const ISO_COS = Math.cos(Math.PI / 6)
const ISO_SIN = 0.5
const HEIGHT_SCALE = 0.95
const BOUNDS_PADDING = 0.05
const CORNER_RADIUS = 0.34
const PATH_STEP = 0.018

// Corridor centre-line vertices. Every vertex is a right-angle turn.
const PATH_VERTICES: Point[] = [
  { x: 0, y: 2 },
  { x: 1, y: 2 },
  { x: 1, y: 4 },
  { x: 3, y: 4 },
  { x: 3, y: 2 },
  { x: 5, y: 2 },
  { x: 5, y: 3 },
  { x: 7, y: 3 },
]

export interface SceneLayout {
  blocks: SceneBlock[]
  /** Uniformly spaced samples along the smoothed path, in normalised scene space. */
  path: Point[]
  /** Path corner nodes, normalised. */
  waypoints: Point[]
  start: Point
  goal: Point
  hazard: Point
  /** Width / height of the scene box. */
  aspect: number
  /** Lattice -> normalised (0..1, y down) for a ground or elevated point. */
  toScene: (x: number, y: number, z?: number) => Point
  /** Inverse of `toScene` on the ground plane (z = 0): normalised scene -> lattice. */
  fromScene: (x: number, y: number) => Point
  /** Normalised screen-y covered by one lattice unit of block height. */
  unitY: number
  /** Lattice-space path samples, parallel to `path`. */
  latticePath: Point[]
  goalLattice: Point
}

function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function rawProject(x: number, y: number, z = 0): Point {
  return { x: (x + y) * ISO_COS, y: (y - x) * ISO_SIN - z * HEIGHT_SCALE }
}

function towards(from: Point, to: Point, distance: number): Point {
  const dx = to.x - from.x
  const dy = to.y - from.y
  const length = Math.hypot(dx, dy) || 1
  return { x: from.x + (dx / length) * distance, y: from.y + (dy / length) * distance }
}

function resample(points: Point[], step: number): Point[] {
  const out: Point[] = [points[0]]
  let carry = 0
  for (let i = 1; i < points.length; i += 1) {
    const a = points[i - 1]
    const b = points[i]
    const segment = Math.hypot(b.x - a.x, b.y - a.y)
    let travelled = step - carry
    while (travelled <= segment) {
      const t = travelled / segment
      out.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t })
      travelled += step
    }
    carry = segment - (travelled - step)
  }
  out.push(points[points.length - 1])
  return out
}

function roundedPath(vertices: Point[]): Point[] {
  const dense: Point[] = [vertices[0]]
  for (let k = 1; k < vertices.length - 1; k += 1) {
    const a = vertices[k - 1]
    const p = vertices[k]
    const b = vertices[k + 1]
    const radius = Math.min(
      CORNER_RADIUS,
      Math.hypot(a.x - p.x, a.y - p.y) / 2,
      Math.hypot(b.x - p.x, b.y - p.y) / 2,
    )
    const p1 = towards(p, a, radius)
    const p2 = towards(p, b, radius)
    const segments = 12
    for (let s = 0; s <= segments; s += 1) {
      const t = s / segments
      const u = 1 - t
      dense.push({
        x: u * u * p1.x + 2 * u * t * p.x + t * t * p2.x,
        y: u * u * p1.y + 2 * u * t * p.y + t * t * p2.y,
      })
    }
  }
  dense.push(vertices[vertices.length - 1])
  return resample(dense, PATH_STEP)
}

function buildBlocks(): SceneBlock[] {
  const rng = mulberry32(0x2c0ffee)
  const blocks: SceneBlock[] = []
  const inset = CORRIDOR_WIDTH / 2
  for (let i = 0; i < GRID_SIZE; i += 1) {
    for (let j = 0; j < GRID_SIZE; j += 1) {
      const roll = rng()
      const heightRoll = rng()
      // A few open plazas keep the maze from reading as a uniform grid.
      if (roll < 0.1) continue
      const height = 0.16 + heightRoll ** 1.5 * 0.55
      blocks.push({
        x0: i + inset,
        x1: i + 1 - inset,
        y0: j + inset,
        y1: j + 1 - inset,
        height,
      })
    }
  }
  return blocks
}

function visibleFaces(block: SceneBlock): Point[][] {
  const { x0, x1, y0, y1, height: h } = block
  const p = (x: number, y: number, z: number) => rawProject(x, y, z)
  return [
    [p(x0, y0, h), p(x1, y0, h), p(x1, y1, h), p(x0, y1, h)], // top
    [p(x0, y0, h), p(x0, y1, h), p(x0, y1, 0), p(x0, y0, 0)], // -x face
    [p(x0, y1, h), p(x1, y1, h), p(x1, y1, 0), p(x0, y1, 0)], // +y face
  ]
}

let cached: SceneLayout | null = null

export function getSceneLayout(): SceneLayout {
  if (cached) return cached

  const blocks = buildBlocks()
  const latticePath = roundedPath(PATH_VERTICES)

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  const extend = (p: Point) => {
    minX = Math.min(minX, p.x)
    maxX = Math.max(maxX, p.x)
    minY = Math.min(minY, p.y)
    maxY = Math.max(maxY, p.y)
  }
  for (const block of blocks) {
    for (const face of visibleFaces(block)) face.forEach(extend)
    extend(rawProject(block.x1, block.y0, block.height))
  }
  latticePath.forEach((p) => extend(rawProject(p.x, p.y)))

  const padX = (maxX - minX) * BOUNDS_PADDING
  const padY = (maxY - minY) * BOUNDS_PADDING * 1.4
  const width = maxX - minX + padX * 2
  const height = maxY - minY + padY * 2

  const toScene = (x: number, y: number, z = 0): Point => {
    const raw = rawProject(x, y, z)
    return { x: (raw.x - minX + padX) / width, y: (raw.y - minY + padY) / height }
  }

  const fromScene = (nx: number, ny: number): Point => {
    const rx = nx * width + minX - padX
    const ry = ny * height + minY - padY
    return { x: (rx / ISO_COS - ry / ISO_SIN) / 2, y: (rx / ISO_COS + ry / ISO_SIN) / 2 }
  }

  const path = latticePath.map((p) => toScene(p.x, p.y))
  const last = PATH_VERTICES[PATH_VERTICES.length - 1]
  const hazardIndex = Math.floor(path.length * 0.55)
  const hazardBase = path[hazardIndex]

  cached = {
    blocks,
    path,
    latticePath,
    waypoints: PATH_VERTICES.slice(1, -1).map((p) => toScene(p.x, p.y)),
    start: path[0],
    goal: toScene(last.x, last.y),
    goalLattice: last,
    hazard: { x: hazardBase.x, y: hazardBase.y - 0.05 },
    aspect: width / height,
    toScene,
    fromScene,
    unitY: HEIGHT_SCALE / height,
  }
  return cached
}

export interface ParticleOptions {
  /** 1 is the full-detail ceiling (~68k particles); the desktop default is 0.45 (~30k). */
  density: number
}

/**
 * Builds the interleaved particle buffer: dense point clouds on the visible
 * faces of every block (brightest on top faces and edges), sparse corridor
 * dust, the luminous path and the goal ellipse.
 */
export function buildParticles({ density }: ParticleOptions): {
  data: Float32Array
  count: number
  /** Per particle: index into `layout.blocks`, or -1 for dust, path and goal. */
  blockIndex: Int16Array
  /** Per particle: height fraction on its block (0 = base, 1 = top). Rises with the block. */
  lift: Float32Array
} {
  const layout = getSceneLayout()
  const rng = mulberry32(0x9e3779b9)
  const out: number[] = []
  // Side-channel metadata for the hover "terrain rise". Recording it never
  // consumes rng values, so the particle buffer itself is unchanged.
  const blockOf: number[] = []
  const liftOf: number[] = []
  let currentBlock = -1
  let currentLift = 0

  const push = (p: Point, size: number, alpha: number) => {
    blockOf.push(currentBlock)
    liftOf.push(currentBlock < 0 ? 0 : currentLift)
    const angle = rng() * Math.PI * 2
    const radius = 0.1 + rng() * 0.45
    out.push(
      p.x,
      p.y,
      p.x + Math.cos(angle) * radius,
      p.y + Math.sin(angle) * radius,
      size,
      Math.min(alpha, 1),
      rng(),
    )
  }
  const sizeOf = (min: number, max: number) => min + rng() * (max - min)
  const count = (amount: number) => {
    const scaled = amount * density
    const whole = Math.floor(scaled)
    return whole + (rng() < scaled - whole ? 1 : 0)
  }

  for (let blockId = 0; blockId < layout.blocks.length; blockId += 1) {
    const block = layout.blocks[blockId]
    currentBlock = blockId
    const { x0, x1, y0, y1, height: h } = block
    const dx = x1 - x0
    const dy = y1 - y0

    // Top face: the brightest, densest surface.
    currentLift = 1
    for (let n = count(dx * dy * 1150); n > 0; n -= 1) {
      const p = layout.toScene(x0 + rng() * dx, y0 + rng() * dy, h)
      push(p, sizeOf(0.9, 2.1), 0.5 + rng() * 0.45)
    }
    // -x face: lit side, denser towards the top edge.
    for (let n = count(dy * h * 620); n > 0; n -= 1) {
      const depth = rng() ** 1.7
      currentLift = 1 - depth
      const p = layout.toScene(x0, y0 + rng() * dy, h * (1 - depth))
      push(p, sizeOf(0.8, 1.8), (0.18 + (1 - depth) * 0.5) * (0.7 + rng() * 0.3))
    }
    // +y face: shadowed side, sparser and dimmer.
    for (let n = count(dx * h * 380); n > 0; n -= 1) {
      const depth = rng() ** 1.5
      currentLift = 1 - depth
      const p = layout.toScene(x0 + rng() * dx, y1, h * (1 - depth))
      push(p, sizeOf(0.7, 1.5), (0.1 + (1 - depth) * 0.3) * (0.7 + rng() * 0.3))
    }
    // Edges: visible silhouette lines read as crisp volume.
    const edge = (ax: number, ay: number, az: number, bx: number, by: number, bz: number) => {
      const length = Math.hypot(bx - ax, by - ay, (bz - az) * HEIGHT_SCALE)
      for (let n = count(length * 120); n > 0; n -= 1) {
        const t = rng()
        currentLift = h > 0 ? (az + (bz - az) * t) / h : 0
        const p = layout.toScene(ax + (bx - ax) * t, ay + (by - ay) * t, az + (bz - az) * t)
        push(p, sizeOf(1.1, 2.3), 0.55 + rng() * 0.4)
      }
    }
    edge(x0, y0, h, x1, y0, h)
    edge(x1, y0, h, x1, y1, h)
    edge(x1, y1, h, x0, y1, h)
    edge(x0, y1, h, x0, y0, h)
    edge(x0, y0, h, x0, y0, 0)
    edge(x0, y1, h, x0, y1, 0)
    edge(x1, y1, h, x1, y1, 0)
    edge(x0, y1, 0, x1, y1, 0)
  }

  currentBlock = -1 // dust, path and goal ring stay put when blocks rise

  // Corridor dust: very few particles on the open ground.
  for (let n = count(520); n > 0; n -= 1) {
    const p = layout.toScene(rng() * GRID_SIZE, rng() * GRID_SIZE)
    push(p, sizeOf(0.7, 1.3), 0.06 + rng() * 0.16)
  }

  // Luminous path, drawn as an unoccluded overlay so the route always reads:
  // a bright core line plus a faint wide halo.
  const pathEvery = density < 0.3 ? 2 : 1
  for (let i = 0; i < layout.path.length; i += pathEvery) {
    push(layout.path[i], 2, 1)
    if (i % 2 === 0) push(layout.path[i], 6, 0.1)
  }

  // Goal ellipse: a lattice circle projects to an isometric ellipse.
  const goal = layout.goalLattice
  for (let n = 0; n < 110; n += 1) {
    const a = (n / 110) * Math.PI * 2
    push(layout.toScene(goal.x + Math.cos(a) * 0.3, goal.y + Math.sin(a) * 0.3), 1.8, 0.8)
  }

  const data = new Float32Array(out)
  return {
    data,
    count: data.length / PARTICLE_STRIDE,
    blockIndex: Int16Array.from(blockOf),
    lift: Float32Array.from(liftOf),
  }
}
