import { useSyncExternalStore } from 'react'
import type { StudioStore } from './studioStore'
import type { FramePayload } from './studioTypes'

/** Subscribe a small component (HUD, 2D renderer) to the live frame stream. */
export function useFrameSnapshot(store: StudioStore): FramePayload | null {
  return useSyncExternalStore(store.subscribeFrame, () => store.frame)
}
