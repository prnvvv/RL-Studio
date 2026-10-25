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
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        flexWrap: 'wrap',
        padding: 'var(--space-2) var(--space-3)',
        border: `1px ${isLive ? 'solid' : 'dashed'} var(--border-primary)`,
        borderRadius: 'var(--radius-sm)',
        background: 'var(--bg-panel)',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: '7px',
          height: '7px',
          borderRadius: '50%',
          border: '1px solid var(--text-primary)',
          background: isLive ? 'var(--text-primary)' : 'transparent',
          flexShrink: 0,
        }}
      />
      <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>{view.label}</span>
      <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
        {view.description}
      </span>
      {lastUpdated ? (
        <span
          style={{
            marginLeft: 'auto',
            fontSize: 'var(--text-xs)',
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-muted)',
          }}
        >
          Last snapshot {lastUpdated}
        </span>
      ) : null}
    </div>
  )
}
