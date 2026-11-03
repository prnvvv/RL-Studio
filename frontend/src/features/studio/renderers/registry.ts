import { gridScene } from '../simulationAdapters'
import { CartPole2D } from './CartPole2D'
import { CartPole3D } from './CartPole3D'
import { GridMaze2D } from './GridMaze2D'
import { GridMaze3D } from './GridMaze3D'
import type { RendererDefinition } from './types'

/**
 * Renderer registry. Keys match `renderer` in the backend environment catalog.
 * An environment without a registered renderer is shown as unavailable rather
 * than drawn with a stand-in.
 */
const registry: Record<string, RendererDefinition> = {
  cartpole: {
    key: 'cartpole',
    label: 'CartPole',
    Scene3D: CartPole3D,
    Scene2D: CartPole2D,
    camera: () => ({ position: [0, 1.4, 6], target: [0, 0.7, 0] }),
  },
  grid_maze: {
    key: 'grid_maze',
    label: 'Warehouse maze',
    Scene3D: GridMaze3D,
    Scene2D: GridMaze2D,
    camera: (scene) => {
      const grid = gridScene(scene)
      const size = grid ? Math.max(grid.rows, grid.cols) : 8
      return { position: [size * 0.55, size * 0.95, size * 0.95], target: [0, 0, 0] }
    },
  },
}

export function getRenderer(key: string | null | undefined): RendererDefinition | null {
  return key ? (registry[key] ?? null) : null
}

export function registeredRenderers(): string[] {
  return Object.keys(registry)
}
