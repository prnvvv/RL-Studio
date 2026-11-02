import { createContext, useContext, type ReactNode } from 'react'
import type { LiveEventsOptions, LiveEventsResult } from '../hooks/useLiveEvents'
import { useLiveEvents } from '../hooks/useLiveEvents'

const LiveEventsContext = createContext<LiveEventsResult | null>(null)

export interface LiveEventsProviderProps {
  /**
   * Selected run, or null when no run is in scope. With no run, no connection
   * is opened and the shared state reports `not_configured` — that is not a
   * claim that training is idle.
   */
  runId: string | null
  /** Injectable transport factory; defaults to the WebSocket stream. */
  createStream?: LiveEventsOptions['createStream']
  children: ReactNode
}

/**
 * Owns the single live-event subscription for the selected run so several
 * panels (connection state, event timeline) read the same stream instead of
 * opening a socket each (`frontend/AGENTS.md` §11.2).
 *
 * The provider only shares transport state and recorded events. It never
 * derives run status from the connection.
 */
export function LiveEventsProvider({ runId, createStream, children }: LiveEventsProviderProps) {
  const live = useLiveEvents(runId, createStream === undefined ? {} : { createStream })
  return <LiveEventsContext.Provider value={live}>{children}</LiveEventsContext.Provider>
}

/** Read the shared live-event state. Requires a `LiveEventsProvider`. */
export function useLiveEventsContext(): LiveEventsResult {
  const value = useContext(LiveEventsContext)
  if (value === null) {
    throw new Error('useLiveEventsContext must be used within a LiveEventsProvider')
  }
  return value
}
