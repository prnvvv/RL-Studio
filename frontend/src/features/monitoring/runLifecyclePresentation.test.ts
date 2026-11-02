import { describe, expect, it } from 'vitest'
import type { RunLifecycle, RunLifecycleState } from '../../schemas/runs'
import {
  canRequestStop,
  canStartRun,
  runLifecyclePresentation,
  runLifecycleRows,
} from './runLifecyclePresentation'

function lifecycle(overrides: Partial<RunLifecycle> = {}): RunLifecycle {
  return {
    runId: 'run_1',
    state: 'running',
    rawStatus: 'running',
    failureReported: false,
    ...overrides,
  }
}

const STATES: RunLifecycleState[] = [
  'created',
  'queued',
  'starting',
  'running',
  'stop_requested',
  'stopped',
  'completed',
  'failed',
  'cancelled',
  'unknown',
  'unrecognized',
]

describe('runLifecyclePresentation', () => {
  it('labels every lifecycle state without inventing one', () => {
    for (const state of STATES) {
      const presentation = runLifecyclePresentation(state)
      expect(presentation.label.trim()).not.toBe('')
      expect(presentation.description.trim()).not.toBe('')
    }
  })

  it('keeps unknown and unrecognised distinct', () => {
    expect(runLifecyclePresentation('unknown').label).toBe('Unknown')
    expect(runLifecyclePresentation('unrecognized').label).toBe('Unrecognised status')
  })

  it('does not describe stop_requested as stopped', () => {
    const presentation = runLifecyclePresentation('stop_requested')

    expect(presentation.label).toBe('Stop requested')
    expect(`${presentation.label} ${presentation.description}`).not.toMatch(/is stopped\b/i)
    expect(presentation.description).toMatch(/not stopped until the backend reports/i)
  })
})

describe('runLifecycleRows', () => {
  it('shows the recorded run id and status verbatim', () => {
    const rows = runLifecycleRows(lifecycle(), '2026-10-25T12:04:09Z')

    expect(rows.find((row) => row.id === 'run_id')?.value).toBe('run_1')
    expect(rows.find((row) => row.id === 'reported_status')?.value).toBe('running')
    expect(rows.find((row) => row.id === 'snapshot')?.value).toBe('2026-10-25 12:04:09Z')
  })

  it('quotes an unrecognised status instead of mapping it onto a state', () => {
    const rows = runLifecycleRows(
      lifecycle({ state: 'unrecognized', rawStatus: 'paused' }),
      '2026-10-25T12:04:09Z',
    )

    expect(rows.find((row) => row.id === 'lifecycle')?.value).toBe('Unrecognised status')
    expect(rows.find((row) => row.id === 'reported_status')?.value).toBe('paused')
  })

  it('reports a missing status read as not recorded rather than a made-up time', () => {
    const rows = runLifecycleRows(lifecycle(), null)

    expect(rows.find((row) => row.id === 'snapshot')?.value).toBe('Not recorded')
  })

  it('reports a missing snapshot for an unparseable timestamp too', () => {
    const rows = runLifecycleRows(lifecycle(), 'not-a-time')

    expect(rows.find((row) => row.id === 'snapshot')?.value).toBe('Not recorded')
  })

  it('shows only that a failure was recorded, never the failure text', () => {
    const rows = runLifecycleRows(
      lifecycle({ state: 'failed', rawStatus: 'failed', failureReported: true }),
      null,
    )

    const failure = rows.find((row) => row.id === 'failure')
    expect(failure?.value).toBe('Yes')
    expect(JSON.stringify(rows)).not.toMatch(/error|traceback|exception/i)
  })

  it('omits the failure row when no failure was recorded', () => {
    const rows = runLifecycleRows(lifecycle(), null)

    expect(rows.find((row) => row.id === 'failure')).toBeUndefined()
  })
})

describe('canStartRun', () => {
  it('allows starting only where no lifecycle has been recorded yet', () => {
    expect(canStartRun('created').allowed).toBe(true)
    expect(canStartRun('unknown').allowed).toBe(true)
  })

  it('blocks starting while a task is recorded and explains why', () => {
    for (const state of ['queued', 'starting', 'running', 'stop_requested'] as const) {
      const availability = canStartRun(state)
      expect(availability.allowed).toBe(false)
      expect(availability.reason).toMatch(/already recorded/i)
    }
  })

  it('blocks restarting a run that already has a terminal result', () => {
    for (const state of ['stopped', 'completed', 'failed', 'cancelled'] as const) {
      const availability = canStartRun(state)
      expect(availability.allowed).toBe(false)
      expect(availability.reason).toMatch(/new run identifier/i)
    }
  })

  it('fails closed for an unrecognised status', () => {
    const availability = canStartRun('unrecognized')

    expect(availability.allowed).toBe(false)
    expect(availability.reason).toMatch(/not recognised/i)
  })
})

describe('canRequestStop', () => {
  it('allows a stop request only while a task may be in flight', () => {
    for (const state of ['queued', 'starting', 'running'] as const) {
      expect(canRequestStop(state).allowed).toBe(true)
    }
  })

  it('blocks a repeated stop once one has been requested', () => {
    const availability = canRequestStop('stop_requested')

    expect(availability.allowed).toBe(false)
    expect(availability.reason).toMatch(/already been requested/i)
  })

  it('blocks stopping when nothing is active', () => {
    for (const state of [
      'created',
      'unknown',
      'stopped',
      'completed',
      'failed',
      'cancelled',
      'unrecognized',
    ] as const) {
      expect(canRequestStop(state).allowed).toBe(false)
    }
  })

  it('never allows a stop request for an unrecognised status', () => {
    expect(canRequestStop('unrecognized').reason).toMatch(/not recognised/i)
  })
})
