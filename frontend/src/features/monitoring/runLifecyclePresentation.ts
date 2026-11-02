/**
 * Run lifecycle presentation — derived, deterministic.
 *
 * Display rules enforced here:
 * - The lifecycle label is derived only from the canonical state mapping in
 *   `schemas/runs.ts`; a backend value the frontend does not recognise is
 *   labelled as unrecognised and quoted verbatim, never coerced.
 * - `unknown` (the worker has no result for this run id) is distinct from
 *   "unrecognised" (the backend sent something new). Neither is treated as a
 *   terminal or active state.
 * - The worker's failure text is never rendered; only the fact that a failure
 *   was recorded is shown, and it is attributed to the backend record.
 * - Timestamps render as "Not recorded" when absent, never as a fabricated
 *   time.
 * - Control availability fails closed: an unrecognised status blocks both
 *   actions, and starting is never offered for a run that already has a
 *   recorded lifecycle, because the start endpoint re-queues work under the
 *   same run identifier and would rewrite that record (root `AGENTS.md` §9).
 */
import type { DefinitionRow } from '../../components/ui/DefinitionList'
import type { RunLifecycle, RunLifecycleState } from '../../schemas/runs'
import { formatUtcDate, formatUtcTime } from '../../utils/datetime'

export type RunLifecycleTone = 'strong' | 'neutral' | 'quiet' | 'warning'

export interface RunLifecyclePresentation {
  label: string
  /** What the state means for the run, without claiming more than is known. */
  description: string
  tone: RunLifecycleTone
}

const PRESENTATION: Record<RunLifecycleState, RunLifecyclePresentation> = {
  created: {
    label: 'Created',
    description: 'The run record exists but no training task has been queued.',
    tone: 'neutral',
  },
  queued: {
    label: 'Queued',
    description: 'The backend accepted a training task and has not started it yet.',
    tone: 'neutral',
  },
  starting: {
    label: 'Starting',
    description: 'The backend reported the training task as starting.',
    tone: 'neutral',
  },
  running: {
    label: 'Running',
    description: 'The backend reported the training task as running.',
    tone: 'strong',
  },
  stop_requested: {
    label: 'Stop requested',
    description:
      'A stop has been requested. The run is not stopped until the backend reports a stopped state.',
    tone: 'neutral',
  },
  stopped: {
    label: 'Stopped',
    description: 'The backend reported the run as stopped.',
    tone: 'quiet',
  },
  completed: {
    label: 'Completed',
    description: 'The backend reported the run as completed.',
    tone: 'quiet',
  },
  failed: {
    label: 'Failed',
    description:
      'The backend recorded a failure for this run. The failure detail is backend-owned and not displayed here.',
    tone: 'warning',
  },
  cancelled: {
    label: 'Cancelled',
    description: 'The backend reported the run as cancelled.',
    tone: 'quiet',
  },
  unknown: {
    label: 'Unknown',
    description: 'The backend has no recorded training task for this run identifier.',
    tone: 'quiet',
  },
  unrecognized: {
    label: 'Unrecognised status',
    description:
      'The backend reported a status this interface does not recognise. It is shown exactly as recorded and is not treated as any lifecycle state.',
    tone: 'quiet',
  },
}

export function runLifecyclePresentation(state: RunLifecycleState): RunLifecyclePresentation {
  return PRESENTATION[state]
}

/** `YYYY-MM-DD HH:MM:SSZ`, or a null-safe "not recorded" label. */
function formatSnapshot(asOf: string | null): string {
  if (asOf === null) return 'Not recorded'
  const date = formatUtcDate(asOf)
  const time = formatUtcTime(asOf)
  if (date === null || time === null) return 'Not recorded'
  return `${date} ${time}`
}

/**
 * Label/value rows for the run lifecycle panel. Every row is either a real
 * recorded value or an explicit not-recorded/unavailable state.
 */
export function runLifecycleRows(
  lifecycle: RunLifecycle,
  snapshotAsOf: string | null,
): DefinitionRow[] {
  const presentation = runLifecyclePresentation(lifecycle.state)

  const rows: DefinitionRow[] = [
    {
      id: 'run_id',
      label: 'Run ID',
      value: lifecycle.runId,
    },
    {
      id: 'lifecycle',
      label: 'Lifecycle state',
      value: presentation.label,
      note: presentation.description,
    },
    {
      id: 'reported_status',
      label: 'Reported status',
      value: lifecycle.rawStatus,
      note: 'As returned by the run status endpoint',
    },
    {
      id: 'snapshot',
      label: 'Status read at',
      value: formatSnapshot(snapshotAsOf),
      note: snapshotAsOf === null ? 'No status response has been received yet' : 'UTC',
    },
  ]

  if (lifecycle.failureReported) {
    rows.push({
      id: 'failure',
      label: 'Failure recorded',
      value: 'Yes',
      note: 'Failure details are retained by the backend and not displayed',
    })
  }

  return rows
}

export interface RunActionAvailability {
  allowed: boolean
  /** Why the action is unavailable; null when it is allowed. */
  reason: string | null
}

const ALLOWED: RunActionAvailability = { allowed: true, reason: null }

function blocked(reason: string): RunActionAvailability {
  return { allowed: false, reason }
}

/**
 * Starting is offered only when nothing has been recorded for the run id yet.
 * The start endpoint re-queues a worker task under the identifier it is given
 * and keeps no history, so re-starting a run that already has a lifecycle
 * would overwrite that record rather than create a new one.
 */
export function canStartRun(state: RunLifecycleState): RunActionAvailability {
  switch (state) {
    case 'created':
    case 'unknown':
      return ALLOWED
    case 'queued':
    case 'starting':
    case 'running':
    case 'stop_requested':
      return blocked('A training task is already recorded for this run.')
    case 'stopped':
    case 'completed':
    case 'failed':
    case 'cancelled':
      return blocked(
        'This run already has a recorded result. Use a new run identifier to start again.',
      )
    case 'unrecognized':
      return blocked('The reported status is not recognised, so starting is blocked.')
  }
}

/**
 * A stop request is offered only for states where a training task is plausibly
 * in flight. It requests a stop; it never claims the run has stopped.
 */
export function canRequestStop(state: RunLifecycleState): RunActionAvailability {
  switch (state) {
    case 'queued':
    case 'starting':
    case 'running':
      return ALLOWED
    case 'stop_requested':
      return blocked('A stop has already been requested for this run.')
    case 'created':
    case 'unknown':
      return blocked('No active training task is recorded for this run.')
    case 'stopped':
    case 'completed':
    case 'failed':
    case 'cancelled':
      return blocked('This run is no longer active.')
    case 'unrecognized':
      return blocked('The reported status is not recognised, so stopping is blocked.')
  }
}
