import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApiClient } from './client'
import { createLiveEventStream } from './events'
import {
  getProjectScope,
  projectScopeHeaders,
  setProjectScope,
  withProjectScope,
} from './projectScope'
import { sessionStreamUrl } from './studio'

const PID = 'prj_0123456789abcdef'

afterEach(() => {
  setProjectScope(null)
  vi.unstubAllGlobals()
})

describe('project scope', () => {
  it('adds nothing when no project is open', () => {
    expect(getProjectScope()).toBeNull()
    expect(projectScopeHeaders()).toEqual({})
    expect(withProjectScope('ws://host/api/v1/events/run_1')).toBe('ws://host/api/v1/events/run_1')
  })

  it('sends the open project as a header on every API request', async () => {
    const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const client = createApiClient({ baseUrl: '' })

    await client.get('/api/v1/studio/history')
    expect(
      new Headers((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].headers).has(
        'X-Project-ID',
      ),
    ).toBe(false)

    setProjectScope(PID)
    await client.get('/api/v1/studio/history')
    await client.post('/api/v1/verification/runs/r/verifications', { jsonBody: {} })
    for (const call of fetchMock.mock.calls.slice(1) as unknown as [string, RequestInit][]) {
      expect(new Headers(call[1].headers).get('X-Project-ID')).toBe(PID)
    }
  })

  it('carries the scope on streams, which cannot set headers', () => {
    setProjectScope(PID)
    expect(withProjectScope('ws://host/api/v1/events/run_1')).toBe(
      `ws://host/api/v1/events/run_1?project_id=${PID}`,
    )
    expect(withProjectScope('/api/x?after=3')).toBe(`/api/x?after=3&project_id=${PID}`)
    expect(sessionStreamUrl('ses_1', 4)).toContain(`project_id=${PID}`)
    expect(sessionStreamUrl('ses_1', 4)).toContain('after=4')

    const urls: string[] = []
    const stream = createLiveEventStream({
      runId: 'run_1',
      baseUrl: 'http://localhost:8000',
      origin: 'http://localhost',
      onState: () => {},
      onEvents: () => {},
      createSocket: (url) => {
        urls.push(url)
        return { close() {}, onopen: null, onmessage: null, onerror: null, onclose: null } as never
      },
    })
    stream.close()
    expect(urls[0]).toBe(`ws://localhost:8000/api/v1/events/run_1?project_id=${PID}`)
  })

  it('stops scoping as soon as the project is closed (no stale scope)', () => {
    setProjectScope(PID)
    setProjectScope(null)
    expect(projectScopeHeaders()).toEqual({})
    expect(sessionStreamUrl('ses_1')).not.toContain('project_id')
  })
})
