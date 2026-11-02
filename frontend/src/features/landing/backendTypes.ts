import type { SceneState } from './sceneState'

export type BackendKind = 'webgl' | 'canvas2d'

export interface BackendCallbacks {
  /** A backend failed or produced nothing; `fatal` means it cannot continue. */
  onProblem(reason: string, fatal: boolean): void
  onContextLost(): void
  onContextRestored(): void
}

export interface RenderBackend {
  readonly kind: BackendKind
  readonly particleCount: number
  /** Milliseconds the last spring-physics step took (0 when idle). */
  lastStepMs: number
  resize(cssWidth: number, cssHeight: number, dpr: number): void
  draw(state: SceneState, dt: number): void
  dispose(): void
}

export type Logger = (...args: unknown[]) => void
