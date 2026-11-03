import { gridScene } from '../simulationAdapters'
import { CartPole2D } from './CartPole2D'
import { CartPole3D } from './CartPole3D'
import { GridMaze2D } from './GridMaze2D'
import { GridMaze3D } from './GridMaze3D'
import { BipedalWalker2D } from './BipedalWalker2D'
import { LunarLander2D } from './LunarLander2D'
import { MountainCar2D } from './MountainCar2D'
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
    // Close enough that the cart and pole fill the view across the whole track.
    camera: () => ({ position: [0, 1.0, 4.4], target: [0, 0.5, 0] }),
  },
  grid_maze: {
    key: 'grid_maze',
    label: 'Warehouse maze',
    Scene3D: GridMaze3D,
    Scene2D: GridMaze2D,
    camera: (scene) => {
      const grid = gridScene(scene)
      const size = grid ? Math.max(grid.rows, grid.cols) : 8
      // Far enough back that the whole board, including the goal corner, stays in frame.
      return { position: [size * 0.62, size * 1.15, size * 1.15], target: [0, 0, 0] }
    },
  },
  // The physics environments below are drawn in 2D only; the viewport says so instead of faking 3D.
  mountain_car: {
    key: 'mountain_car',
    label: 'MountainCar',
    Scene2D: MountainCar2D,
    camera: () => ({ position: [0, 0, 5], target: [0, 0, 0] }),
  },
  lunar_lander: {
    key: 'lunar_lander',
    label: 'LunarLander',
    Scene2D: LunarLander2D,
    camera: () => ({ position: [0, 0, 5], target: [0, 0, 0] }),
  },
  bipedal_walker: {
    key: 'bipedal_walker',
    label: 'BipedalWalker',
    Scene2D: BipedalWalker2D,
    camera: () => ({ position: [0, 0, 5], target: [0, 0, 0] }),
  },
}

export function getRenderer(key: string | null | undefined): RendererDefinition | null {
  return key ? (registry[key] ?? null) : null
}

export function registeredRenderers(): string[] {
  return Object.keys(registry)
}
