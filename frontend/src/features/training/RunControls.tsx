import { useState } from 'react'
import { ConfirmationDialog } from '../../components/ui/ConfirmationDialog'
import type { RunLifecycle } from '../../schemas/runs'
import type { RunService, RunStopAcknowledgement } from '../../services/runs'
import { canRequestStop, canStartRun } from '../monitoring/runLifecyclePresentation'

export interface RunControlsProps {
  /** Identifier the controls act on. Empty disables both actions. */
  runId: string
  /**
   * Last lifecycle the backend reported for `runId`, or null when none has
   * been read yet. Nothing is assumed while it is null: both actions fail
   * closed instead of guessing that the run is startable or stoppable.
   */
  lifecycle: RunLifecycle | null
  service: RunService
  /** Called after the backend acknowledges a start or stop so the page re-reads status. */
  onAcknowledged: (outcome: RunControlOutcome) => void
}

export type RunControlOutcome =
  | { kind: 'started'; acknowledgement: RunLifecycle }
  | { kind: 'stop_requested'; acknowledgement: RunStopAcknowledgement }

type Notice =
  | { tone: 'info'; message: string }
  | { tone: 'warning'; message: string }
  | { tone: 'error'; message: string }

const START_UNCERTAIN =
  'The start request did not complete. The backend may or may not have queued a task for this run. Check the run status before trying again — this page does not retry automatically.'
const STOP_UNCERTAIN =
  'The stop request did not complete. No stop is confirmed. Check the run status before trying again — this page does not retry automatically.'

/**
 * Start/stop controls for the operational run endpoints.
 *
 * Truthfulness rules:
 * - A start acknowledgement is reported as "accepted with status X", never as
 *   "training started" and never as progress.
 * - A stop acknowledgement is reported as "stop requested", never as stopped;
 *   the lifecycle shown afterwards always comes from the status endpoint.
 * - A timeout or network failure leaves the outcome explicitly unknown and is
 *   never retried automatically (the start endpoint has no idempotency key).
 * - Both buttons are disabled while a request is in flight so a double
 *   submission cannot queue duplicate work.
 * - Availability comes from `runLifecyclePresentation` and is stated in text,
 *   not implied by a disabled style alone.
 */
export function RunControls({ runId, lifecycle, service, onAcknowledged }: RunControlsProps) {
  const [pending, setPending] = useState<'start' | 'stop' | null>(null)
  const [confirmingStop, setConfirmingStop] = useState(false)
  const [notice, setNotice] = useState<Notice | null>(null)

  const startAvailability =
    runId.trim() === ''
      ? { allowed: false, reason: 'Enter a run identifier first.' }
      : lifecycle === null
        ? {
            allowed: false,
            reason: 'The current run state has not been read, so starting is blocked.',
          }
        : canStartRun(lifecycle.state)

  const stopAvailability =
    runId.trim() === ''
      ? { allowed: false, reason: 'Enter a run identifier first.' }
      : lifecycle === null
        ? {
            allowed: false,
            reason: 'The current run state has not been read, so stopping is blocked.',
          }
        : canRequestStop(lifecycle.state)

  async function requestStart() {
    if (pending !== null || !startAvailability.allowed) return
    setPending('start')
    setNotice(null)

    const result = await service.startRun({ run_id: runId })
    setPending(null)

    if (result.state === 'ok') {
      setNotice({
        tone: 'info',
        message: `The backend accepted the start request for run ${result.data.runId} and reported status "${result.data.rawStatus}". Training progress is not reported by this endpoint.`,
      })
      onAcknowledged({ kind: 'started', acknowledgement: result.data })
      return
    }

    if (
      result.error.kind === 'timeout' ||
      result.error.kind === 'network' ||
      result.error.kind === 'cancelled'
    ) {
      setNotice({ tone: 'warning', message: START_UNCERTAIN })
      return
    }

    setNotice({ tone: 'error', message: result.error.message })
  }

  async function requestStop() {
    if (pending !== null || !stopAvailability.allowed) return
    setConfirmingStop(false)
    setPending('stop')
    setNotice(null)

    const result = await service.stopRun(runId)
    setPending(null)

    if (result.state === 'ok') {
      setNotice({
        tone: 'info',
        message: `Stop requested for run ${result.data.runId}. The run is not stopped until the backend reports a stopped state.`,
      })
      onAcknowledged({ kind: 'stop_requested', acknowledgement: result.data })
      return
    }

    if (
      result.error.kind === 'timeout' ||
      result.error.kind === 'network' ||
      result.error.kind === 'cancelled'
    ) {
      setNotice({ tone: 'warning', message: STOP_UNCERTAIN })
      return
    }

    setNotice({ tone: 'error', message: result.error.message })
  }

  const busy = pending !== null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={() => {
            void requestStart()
          }}
          disabled={!startAvailability.allowed || busy}
          aria-busy={pending === 'start' || undefined}
          style={{
            padding: '8px 16px',
            background: 'var(--text-primary)',
            color: 'var(--bg-primary)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            cursor: !startAvailability.allowed || busy ? 'not-allowed' : 'pointer',
            opacity: !startAvailability.allowed || busy ? 0.6 : 1,
            fontFamily: 'var(--font-sans)',
            fontSize: 'var(--text-sm)',
            fontWeight: 600,
          }}
        >
          {pending === 'start' ? 'Starting…' : 'Start training'}
        </button>

        <button
          type="button"
          onClick={() => setConfirmingStop(true)}
          disabled={!stopAvailability.allowed || busy}
          aria-busy={pending === 'stop' || undefined}
          style={{
            padding: '8px 16px',
            background: 'transparent',
            color: 'var(--text-primary)',
            border: '1px dashed var(--border-primary)',
            borderRadius: 'var(--radius-sm)',
            cursor: !stopAvailability.allowed || busy ? 'not-allowed' : 'pointer',
            opacity: !stopAvailability.allowed || busy ? 0.6 : 1,
            fontFamily: 'var(--font-sans)',
            fontSize: 'var(--text-sm)',
          }}
        >
          {pending === 'stop' ? 'Stop requested…' : 'Stop run'}
        </button>
      </div>

      {!startAvailability.allowed && startAvailability.reason && (
        <p
          style={{
            margin: 0,
            fontSize: 'var(--text-xs)',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          Start unavailable: {startAvailability.reason}
        </p>
      )}
      {!stopAvailability.allowed && stopAvailability.reason && (
        <p
          style={{
            margin: 0,
            fontSize: 'var(--text-xs)',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          Stop unavailable: {stopAvailability.reason}
        </p>
      )}

      {notice && (
        <p
          role={notice.tone === 'error' ? 'alert' : 'status'}
          style={{
            margin: 0,
            fontSize: 'var(--text-xs)',
            color: notice.tone === 'error' ? 'var(--text-primary)' : 'var(--text-secondary)',
            borderTop: '1px solid var(--border-secondary)',
            paddingTop: 'var(--space-2)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          {notice.message}
        </p>
      )}

      <p
        style={{
          margin: 0,
          fontSize: 'var(--text-xs)',
          color: 'var(--text-muted)',
          fontFamily: 'var(--font-sans)',
        }}
      >
        These endpoints are provisional placeholders in the backend. A start request queues a worker
        task; it is not yet connected to the PPO trainer, so no training metrics are reported for
        it.
      </p>

      {confirmingStop && (
        <ConfirmationDialog
          title="Request a stop for this run?"
          body={
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <span>
                This requests a stop for run <strong>{runId}</strong>. It does not stop the run
                itself, and it is not evidence that training has ended.
              </span>
              <span>
                The displayed lifecycle is re-read from the backend after the request; it stays
                unchanged until the backend reports a new state.
              </span>
            </div>
          }
          confirmLabel="Request stop"
          cancelLabel="Cancel"
          destructive
          pending={pending === 'stop'}
          onConfirm={() => {
            void requestStop()
          }}
          onCancel={() => setConfirmingStop(false)}
        />
      )}
    </div>
  )
}
