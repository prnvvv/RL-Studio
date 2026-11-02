import { afterEach, describe, expect, it, vi } from 'vitest'
import { createRunService, runStartPath, runStatusPath, runStopPath } from './runs'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('run service paths', () => {
  it('targets only the documented operational routes and encodes identifiers', () => {
    expect(runStatusPath('run 1')).toBe('/api/v1/runs/run%201/status')
    expect(runStopPath('run/1')).toBe('/api/v1/runs/run%2F1/stop')
    expect(runStartPath()).toBe('/api/v1/runs/start')
  })
})

describe('getRunStatus', () => {
  it('returns the mapped lifecycle for a valid status payload', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ run_id: 'run_1', status: 'running' })),
    )

    const result = await createRunService().getRunStatus('run_1')

    expect(result).toEqual({
      state: 'ok',
      data: {
        runId: 'run_1',
        state: 'running',
        rawStatus: 'running',
        failureReported: false,
      },
    })
  })

  it('preserves an unrecognised backend status instead of coercing it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ run_id: 'run_1', status: 'paused' })),
    )

    const result = await createRunService().getRunStatus('run_1')

    expect(result.state).toBe('ok')
    if (result.state === 'ok') {
      expect(result.data.state).toBe('unrecognized')
      expect(result.data.rawStatus).toBe('paused')
    }
  })

  it('reports a failure without exposing the backend failure text', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse({ run_id: 'run_1', status: 'failed', error: 'C:\\secret\\path' }),
      ),
    )

    const result = await createRunService().getRunStatus('run_1')

    expect(result.state).toBe('ok')
    if (result.state === 'ok') {
      expect(result.data.failureReported).toBe(true)
      expect(JSON.stringify(result.data)).not.toContain('secret')
    }
  })

  it('maps a 404 to not_found and a malformed body to unexpected', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('', { status: 404 })),
    )
    expect(await createRunService().getRunStatus('run_1')).toEqual({
      state: 'error',
      error: { kind: 'not_found', message: expect.any(String), status: 404 },
    })

    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ status: 'running' })),
    )
    expect(await createRunService().getRunStatus('run_1')).toEqual({
      state: 'error',
      error: {
        kind: 'unexpected',
        message: 'The service returned an unexpected response.',
      },
    })
  })

  it('reports a cancelled request without inferring a terminal state', async () => {
    const controller = new AbortController()
    controller.abort()

    const result = await createRunService().getRunStatus('run_1', controller.signal)

    expect(result).toEqual({
      state: 'error',
      error: { kind: 'cancelled', message: expect.any(String) },
    })
  })
})

describe('startRun', () => {
  it('sends only the run identifier the endpoint reads', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ run_id: 'run_1', status: 'queued' }, 200))
    vi.stubGlobal('fetch', fetchMock)

    const result = await createRunService().startRun({ run_id: 'run_1' })

    expect(result).toEqual({
      state: 'ok',
      data: {
        runId: 'run_1',
        state: 'queued',
        rawStatus: 'queued',
        failureReported: false,
      },
    })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/runs/start')
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ run_id: 'run_1' }))
  })

  it('does not retry a failed start automatically', async () => {
    const fetchMock = vi.fn(async () => new Response('', { status: 503 }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await createRunService().startRun({ run_id: 'run_1' })

    expect(result.state).toBe('error')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('rejects an acknowledgement without a run id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ status: 'queued' })),
    )

    const result = await createRunService().startRun({ run_id: 'run_1' })

    expect(result.state).toBe('error')
    if (result.state === 'error') expect(result.error.kind).toBe('unexpected')
  })
})

describe('stopRun', () => {
  it('reports the acknowledgement as stop_requested, not as stopped', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse({ run_id: 'run_1', status: 'stop_requested', idempotent: true }),
      ),
    )

    const result = await createRunService().stopRun('run_1')

    expect(result).toEqual({
      state: 'ok',
      data: {
        runId: 'run_1',
        state: 'stop_requested',
        rawStatus: 'stop_requested',
        idempotent: true,
      },
    })
    if (result.state === 'ok') expect(result.data.state).not.toBe('stopped')
  })

  it('surfaces a conflict as a stable error rather than retrying', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('', { status: 409 })),
    )

    const result = await createRunService().stopRun('run_1')

    expect(result).toEqual({
      state: 'error',
      error: { kind: 'conflict', message: expect.any(String), status: 409 },
    })
  })
})
