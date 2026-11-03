import type { ComponentType } from 'react'
import type { StudioStore } from '../studioStore'
import type { ScenePalette } from './palette'

export interface RendererProps {
  scene: Record<string, unknown> | null
  store: StudioStore
  palette: ScenePalette
}

export interface CameraSetup {
  position: [number, number, number]
  target: [number, number, number]
}

/** One renderer pair per backend environment `renderer` key. */
export interface RendererDefinition {
  key: string
  label: string
  /** Three.js scene contents (rendered inside a Canvas). Absent for 2D-only environments. */
  Scene3D?: ComponentType<RendererProps>
  /** Flat SVG view; also the fallback when WebGL is unavailable. */
  Scene2D: ComponentType<RendererProps>
  camera: (scene: Record<string, unknown> | null) => CameraSetup
}
