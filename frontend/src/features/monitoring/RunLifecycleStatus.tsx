import { DefinitionList } from '../../components/ui/DefinitionList'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingSkeleton } from '../../components/ui/LoadingSkeleton'
import { StaleDataNotice } from '../../components/ui/StaleDataNotice'
import type { RunLifecycle } from '../../schemas/runs'
import { formatUtcTime } from '../../utils/datetime'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'
import { runLifecycleRows } from './runLifecyclePresentation'

export interface RunLifecycleStatusProps {
  state: ServiceQueryState<RunLifecycle>
  /** ISO time of the last successful status read, or null. */
  snapshotAsOf: string | null
  /** Re-read the status endpoint. Always safe: it is a read. */
  onRefresh: () => void
}

function RefreshButton({ onRefresh }: { onRefresh: () => void }) {
  return (
    <button
      type="button"
      onClick={onRefresh}
      style={{
        padding: '4px 12px',
        background: 'transparent',
        border: '1px solid var(--border-primary)',
        borderRadius: 'var(--radius-sm)',
        color: 'var(--text-primary)',
        cursor: 'pointer',
        fontFamily: 'var(--font-sans)',
      }}
    >
      Refresh status
    </button>
  )
}

/**
 * Renders the backend-authoritative run lifecycle.
 *
 * - A failed status read keeps the last recorded lifecycle visible next to an
 *   explicit stale notice; it never replaces the state with a guess or implies
 *   the run stopped.
 * - A first read failure shows an error with a safe retry, because reading the
 *   status endpoint has no side effects.
 * - Nothing here reports training progress, metrics, or stage completion: the
 *   status endpoint supplies a lifecycle string and nothing else.
 */
export function RunLifecycleStatus({ state, snapshotAsOf, onRefresh }: RunLifecycleStatusProps) {
  if (state.state === 'loading') {
    return <LoadingSkeleton rows={4} />
  }

  if (state.state === 'error') {
    if (state.data === null) {
      return (
        <ErrorState
          title="Run status unavailable"
          description={state.error.message}
          action={<RefreshButton onRefresh={onRefresh} />}
        />
      )
    }

    const asOf = snapshotAsOf === null ? undefined : (formatUtcTime(snapshotAsOf) ?? undefined)
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <StaleDataNotice asOf={asOf} subject="Run status" />
        </div>
        <DefinitionList rows={runLifecycleRows(state.data, snapshotAsOf)} />
        <p
          style={{
            margin: 0,
            fontSize: 'var(--text-xs)',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          {state.error.message} The state above is the last status the backend reported and may no
          longer be current.
        </p>
        <div>
          <RefreshButton onRefresh={onRefresh} />
        </div>
      </div>
    )
  }

  return <DefinitionList rows={runLifecycleRows(state.data, snapshotAsOf)} />
}
