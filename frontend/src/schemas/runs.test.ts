import { describe, expect, it } from 'vitest'
import {
  isActiveRunState,
  isCanonicalRunState,
  isTerminalRunState,
  parseRunStartPayload,
  parseRunStatusPayload,
  parseRunStopPayload,
  toRunLifecycle,
  toRunLifecycleState,
} from './runs'

describe('run lifecycle mapping', () => {
  it('maps every canonical state without alteration', () => {
    for (const state of [
      'created',
      'queued',
      'starting',
      'running',
      'stop_requested',
      'stopped',
      'completed',
      'failed',
      'cancelled',
    ] as const) {
      expect(toRunLifecycleState(state)).toBe(state)
      expect(toRunLifecycleState(` ${state} `)).toBe(state)
    }
  })

  it('keeps the backend "unknown" answer distinct from an unrecognised value', () => {
    expect(toRunLifecycleState('unknown')).toBe('unknown')
    expect(toRunLifecycleState('warm_starting')).toBe('unrecognized')
  })

  it('never coerces an unrecognised status into a lifecycle state', () => {
    const lifecycle = toRunLifecycle({ run_id: 'run_1', status: 'paused' })

    expect(lifecycle.state).toBe('unrecognized')
    expect(lifecycle.rawStatus).toBe('paused')
  })

  it('flags a failure without exposing the backend failure text', () => {
    const lifecycle = toRunLifecycle({
      run_id: 'run_1',
      status: 'failed',
      error: 'Traceback: internal path leaked',
    })

    expect(lifecycle.failureReported).toBe(true)
    expect(lifecycle).not.toHaveProperty('error')
  })
})

describe('run lifecycle predicates', () => {
  it('treats only canonical terminal states as terminal', () => {
    expect(isTerminalRunState('completed')).toBe(true)
    expect(isTerminalRunState('failed')).toBe(true)
    expect(isTerminalRunState('stopped')).toBe(true)
    expect(isTerminalRunState('cancelled')).toBe(true)
    expect(isTerminalRunState('running')).toBe(false)
  })

  it('never treats unknown or unrecognised values as terminal or active', () => {
    for (const state of ['unknown', 'unrecognized'] as const) {
      expect(isTerminalRunState(state)).toBe(false)
      expect(isActiveRunState(state)).toBe(false)
    }
  })

  it('identifies the states in which a stop request is meaningful', () => {
    for (const state of ['queued', 'starting', 'running', 'stop_requested'] as const) {
      expect(isActiveRunState(state)).toBe(true)
    }
    for (const state of ['created', 'stopped', 'completed', 'failed', 'cancelled'] as const) {
      expect(isActiveRunState(state)).toBe(false)
    }
  })

  it('recognises only listed canonical values', () => {
    expect(isCanonicalRunState('running')).toBe(true)
    expect(isCanonicalRunState('unknown')).toBe(false)
    expect(isCanonicalRunState('RUNNING')).toBe(false)
  })
})

describe('payload validation', () => {
  it('accepts the documented status shape and rejects anything else', () => {
    expect(parseRunStatusPayload({ run_id: 'run_1', status: 'running' })).toEqual({
      run_id: 'run_1',
      status: 'running',
    })
    expect(parseRunStatusPayload({ run_id: 'run_1', status: 'failed', error: 'boom' })).toEqual({
      run_id: 'run_1',
      status: 'failed',
      error: 'boom',
    })

    expect(parseRunStatusPayload(null)).toBeNull()
    expect(parseRunStatusPayload({})).toBeNull()
    expect(parseRunStatusPayload({ run_id: '', status: 'running' })).toBeNull()
    expect(parseRunStatusPayload({ run_id: 'run_1' })).toBeNull()
    expect(parseRunStatusPayload({ run_id: 'run_1', status: 42 })).toBeNull()
    expect(parseRunStatusPayload({ run_id: 'run_1', status: 'running', error: {} })).toBeNull()
  })

  it('accepts the documented stop shape and rejects anything else', () => {
    expect(parseRunStopPayload({ run_id: 'run_1', status: 'stop_requested' })).toEqual({
      run_id: 'run_1',
      status: 'stop_requested',
    })
    expect(
      parseRunStopPayload({ run_id: 'run_1', status: 'stop_requested', idempotent: true }),
    ).toEqual({ run_id: 'run_1', status: 'stop_requested', idempotent: true })

    expect(parseRunStopPayload({ run_id: 'run_1' })).toBeNull()
    expect(
      parseRunStopPayload({ run_id: 'run_1', status: 'stop_requested', idempotent: 'yes' }),
    ).toBeNull()
  })

  it('accepts the documented start shape and rejects anything else', () => {
    expect(parseRunStartPayload({ run_id: 'run_1', status: 'queued' })).toEqual({
      run_id: 'run_1',
      status: 'queued',
    })
    expect(parseRunStartPayload({ status: 'queued' })).toBeNull()
    expect(parseRunStartPayload({ run_id: 'run_1' })).toBeNull()
  })
})
