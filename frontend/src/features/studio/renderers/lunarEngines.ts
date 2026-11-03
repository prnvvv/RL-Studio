import type { FramePayload } from '../studioTypes'

/** Which engines fired, read from the action the agent actually took (discrete or continuous). */
export function lunarEngines(frame: FramePayload | null): { main: number; side: -1 | 0 | 1 } {
  const action = frame?.action
  if (frame?.initial || action === null || action === undefined) return { main: 0, side: 0 }
  if (typeof action === 'number') {
    // Discrete: 0 noop, 1 fire left engine, 2 main engine, 3 fire right engine.
    return { main: action === 2 ? 1 : 0, side: action === 1 ? -1 : action === 3 ? 1 : 0 }
  }
  const [throttle = 0, lateral = 0] = action
  return {
    main: throttle > 0 ? Math.min(1, 0.5 + throttle * 0.5) : 0,
    side: Math.abs(lateral) > 0.5 ? (lateral > 0 ? 1 : -1) : 0,
  }
}
