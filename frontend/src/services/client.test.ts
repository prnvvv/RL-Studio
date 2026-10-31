import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { buildRequestUrl, createApiClient } from './client'

// Deterministic stub for a JSON API response.
function jsonResponse(status: number, body: unknown, headers: HeadersInit = {}): Response {
  const bodyText = status === 204 ? null : body === undefined ? '' : JSON.stringify(body)
  const response = new Response(bodyText, {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  })
  return response
}

// A fetch stub whose promise hangs forever but honours the abort signal, as a
// real fetch does — aborting the signal rejects the underlying request.
function unreachable(_url: string, init?: RequestInit): Promise<Response> {
  return new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => {
      reject(new DOMException('The operation was aborted.', 'AbortError'))
    })
  })
}

describe('buildRequestUrl', () => {
  it('joins the base URL and path, stripping trailing slashes', () => {
    expect(buildRequestUrl('http://localhost:8000/', '/api/v1/runs/x/status')).toBe(
      'http://localhost:8000/api/v1/runs/x/status',
    )
  })

  it('uses the path as-is when no base URL is configured', () => {
    expect(buildRequestUrl('', '/api/v1/incidents/x/impact')).toBe('/api/v1/incidents/x/impact')
  })

  it('rejects a path that does not start with a slash', () => {
    expect(() => buildRequestUrl('http://localhost:8000', 'api/v1/runs')).toThrow()
  })
})

describe('client error mapping', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns ok with parsed JSON for a 2xx response', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(200, { run_id: 'run_1' })))
    const client = createApiClient()
    const result = await client.get<{ run_id: string }>('/api/v1/runs/run_1/status')
    expect(result).toEqual({ state: 'ok', data: { run_id: 'run_1' } })
  })

  it('represents 204 responses as ok with null instead of inventing a body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(204, undefined)))
    const client = createApiClient()
    const result = await client.get<null>('/api/v1/runs/run_1/stop')
    expect(result).toEqual({ state: 'ok', data: null })
  })

  it('maps an empty 2xx body to ok(null)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('', { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )
    const client = createApiClient()
    const result = await client.get<null>('/x')
    expect(result).toEqual({ state: 'ok', data: null })
  })

  it('reports a 2xx response with a non-JSON body as unexpected', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('<html>gateway</html>', { status: 200 })),
    )
    const client = createApiClient()
    const result = await client.get<{ a: number }>('/x')
    expect(result.state).toBe('error')
    if (result.state === 'error') {
      expect(result.error.kind).toBe('unexpected')
      // The raw body must never leak into the user-facing message.
      expect(result.error.message).not.toContain('gateway')
    }
  })

  it('maps validation, conflict, rate-limit, unavailable and server statuses', async () => {
    const cases: Array<[number, string]> = [
      [400, 'invalid_request'],
      [422, 'invalid_request'],
      [401, 'unauthorized'],
      [403, 'unauthorized'],
      [404, 'not_found'],
      [409, 'conflict'],
      [429, 'rate_limited'],
      [503, 'unavailable'],
      [500, 'server_error'],
      [502, 'server_error'],
    ]
    for (const [status, kind] of cases) {
      vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(status, { detail: 'backend detail' })))
      const client = createApiClient()
      const result = await client.get<unknown>('/x')
      if (result.state !== 'error') {
        throw new Error(`expected error for status ${status}`)
      }
      expect(result.error.kind).toBe(kind)
      expect(result.error.status).toBe(status)
      // Backend detail strings stay out of the displayable message.
      expect(result.error.message).not.toContain('backend detail')
    }
  })

  it('maps a fetch failure to network without implying the operation failed', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    }))
    const client = createApiClient()
    const result = await client.get<unknown>('/x')
    expect(result.state).toBe('error')
    if (result.state === 'error') {
      expect(result.error.kind).toBe('network')
      expect(result.error.message).toContain('unknown')
    }
  })

  it('never throws: hung requests resolve into a timeout result', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('fetch', vi.fn(unreachable))
    const client = createApiClient({ timeoutMs: 1_000 })
    const pending = client.get<unknown>('/x')
    await vi.advanceTimersByTimeAsync(1_000)
    const result = await pending
    expect(result.state).toBe('error')
    if (result.state === 'error') {
      expect(result.error.kind).toBe('timeout')
      expect(result.error.message).toContain('unknown')
    }
    vi.useRealTimers()
  })

  it('reports a caller-aborted request as cancelled before sending', async () => {
    const fetchMock = vi.fn(unreachable)
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()
    controller.abort()
    const client = createApiClient()
    const result = await client.get<unknown>('/x', { signal: controller.signal })
    expect(result.state).toBe('error')
    if (result.state === 'error') {
      expect(result.error.kind).toBe('cancelled')
    }
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('client request construction', () => {
  it('serializes a JSON body and sets the content type', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { status: 'queued' }))
    vi.stubGlobal('fetch', fetchMock)
    const client = createApiClient({ baseUrl: 'http://localhost:8000' })
    await client.post('/api/v1/runs/start', { jsonBody: { run_id: 'run_1' } })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('http://localhost:8000/api/v1/runs/start')
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ run_id: 'run_1' }))
    const headers = init.headers as Headers
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.get('Accept')).toBe('application/json')
  })
})
