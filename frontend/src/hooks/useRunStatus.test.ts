import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RunLifecycle } from '../schemas/runs'
import type { RunService } from '../services/runs'
import type { ServiceResult } from '../services/types'
import { useRunStatus } from './useRunStatus'

function lifecycle(status: string): RunLifecycle {
  return {
    runId: 'run_1',
    state: status === 'unknown' ? 'unknown' : (status as RunLifecycle['state']),
    rawStatus: status,
    failureReported: status === 'failed',
  }
}

function serviceReturning(
  ...results: Array<ServiceResult<RunLifecycle>>
): RunService & { calls: number } {
  const service = {
    calls: 0,
    async getRunStatus() {
      const result = results[Math.min(service.calls, results.length - 1)]
      service.calls += 1
      return result
    },
    async startRun() {
      throw new Error('not used')
    },
    async stopRun() {
      throw new Error('not used')
    },
  }
  return service as RunService & { calls: number }
}

const ok = (status: string): ServiceResult<RunLifecycle> => ({
  state: 'ok',
  data: lifecycle(status),
})

/** Let the pending service promise settle without moving the fake clock. */
async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
    await Promise.resolve()
    await Promise.resolve()
  })
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useRunStatus', () => {
  it('starts loading, then reports the backend lifecycle', async () => {
    const service = serviceReturning(ok('running'))
    const { result } = renderHook(() => useRunStatus('run_1', service, { intervalMs: 1_000 }))

    expect(result.current.state.state).toBe('loading')
    await flush()

    expect(result.current.state.state).toBe('ok')
    expect(result.current.lastUpdated).not.toBeNull()
    expect(result.current.stale).toBe(false)
    if (result.current.state.state === 'ok') {
      expect(result.current.state.data.state).toBe('running')
    }
  })

  it('polls while non-terminal and stops at a canonical terminal state', async () => {
    const service = serviceReturning(ok('running'), ok('completed'))
    renderHook(() => useRunStatus('run_1', service, { intervalMs: 1_000 }))

    await flush()
    expect(service.calls).toBe(1)

    await advance(1_000)
    expect(service.calls).toBe(2)

    await advance(5_000)
    expect(service.calls).toBe(2)
  })

  it('keeps polling for unknown and unrecognised states, which are not terminal', async () => {
    const service = serviceReturning(ok('unknown'), ok('paused'), ok('running'))
    renderHook(() => useRunStatus('run_1', service, { intervalMs: 1_000 }))

    await flush()
    expect(service.calls).toBe(1)

    await advance(1_000)
    expect(service.calls).toBe(2)

    await advance(1_000)
    expect(service.calls).toBe(3)
  })

  it('retains the last recorded state and marks it stale when a poll fails', async () => {
    const service = serviceReturning(ok('running'), {
      state: 'error',
      error: { kind: 'network', message: 'The service could not be reached.' },
    })
    const { result } = renderHook(() => useRunStatus('run_1', service, { intervalMs: 1_000 }))

    await flush()
    expect(result.current.state.state).toBe('ok')

    await advance(1_000)

    expect(result.current.stale).toBe(true)
    expect(result.current.state.state).toBe('error')
    if (result.current.state.state === 'error') {
      // The earlier lifecycle is retained, not replaced by a guessed state.
      expect(result.current.state.data?.state).toBe('running')
    }
  })

  it('reports a first-poll failure as an error with no retained data', async () => {
    const service = serviceReturning({
      state: 'error',
      error: { kind: 'timeout', message: 'The request timed out.' },
    })
    const { result } = renderHook(() => useRunStatus('run_1', service, { intervalMs: 1_000 }))

    await flush()

    expect(result.current.state.state).toBe('error')
    expect(result.current.stale).toBe(false)
    if (result.current.state.state === 'error') {
      expect(result.current.state.data).toBeNull()
    }
    expect(result.current.lastUpdated).toBeNull()
  })
})
