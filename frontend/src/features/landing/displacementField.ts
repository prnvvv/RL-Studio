import { getSceneLayout, PARTICLE_STRIDE, type Point } from './sceneGeometry'
import { SpringField } from './springField'
import { TerrainField } from './terrainField'

/** Per-particle (x, y) displacement driven by the cursor, simulated on the CPU. */
export interface DisplacementField {
  readonly displacement: Float32Array
  /** Returns true when the displacement changed and needs re-uploading. */
  step(dt: number, mouse: Point, amount: number, aspect: number): boolean
}

export interface ParticleSet {
  data: Float32Array
  count: number
  blockIndex: Int16Array
  lift: Float32Array
}

/**
 * `terrain` (default): blocks rise around the cursor, Terrain-style.
 * Otherwise: the original particle repel (`?terrain=0`).
 */
export function createDisplacementField(
  particles: ParticleSet,
  terrain: boolean,
): DisplacementField {
  return terrain
    ? new TerrainField(particles.blockIndex, particles.lift, getSceneLayout())
    : new SpringField(particles.data, PARTICLE_STRIDE, particles.count)
}
