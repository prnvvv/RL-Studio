export type LiveConnectionState =
  'not_configured' | 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'stale'

const presentation: Record<
  LiveConnectionState,
  { label: string; description: string; emphasis: 'normal' | 'muted' }
> = {
  not_configured: {
    label: 'Live updates not configured',
    description:
      'No live-update transport is connected. Values shown are only what was last recorded.',
    emphasis: 'muted',
  },
  connecting: {
    label: 'Connecting',
    description: 'Establishing the live-update connection.',
    emphasis: 'muted',
  },
  connected: {
    label: 'Live',
    description: 'Receiving recorded events from the backend.',
    emphasis: 'normal',
  },
  reconnecting: {
    label: 'Reconnecting',
    description:
      'The live-update connection dropped and is retrying. Displayed values may be stale.',
    emphasis: 'muted',
  },
  disconnected: {
    label: 'Disconnected',
    description:
      'The live-update connection is closed. Training status is unchanged; displayed values may be stale.',
    emphasis: 'muted',
  },
  stale: {
    label: 'Stale data',
    description:
      'Last known values are shown. They have not been refreshed since the last snapshot.',
    emphasis: 'muted',
  },
}

interface LiveConnectionStatusProps {
  state: LiveConnectionState
  /** When the last snapshot was received, already formatted for display. */
  lastUpdated?: string | null
}

/**
 * Connection state is shown separately from training status: a lost connection
 * is never reported as a failed or stopped run.
 */
export function LiveConnectionStatus({ state, lastUpdated }: LiveConnectionStatusProps) {
  const view = presentation[state]
  const isLive = state === 'connected'

  return (
    <div
      role="status"
      aria-label="Live update connection status"
      className="mon-status"
      data-live={isLive}
    >
      <span aria-hidden="true" className="mon-status__dot" />
      <span className="mon-status__label">{view.label}</span>
      <span aria-hidden="true" className="mon-status__sep" />
      <span className="mon-status__description">{view.description}</span>
      {lastUpdated ? (
        <span className="mon-status__snapshot">Last snapshot {lastUpdated}</span>
      ) : null}
    </div>
  )
}
