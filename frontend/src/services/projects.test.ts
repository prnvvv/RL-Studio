import { afterEach, describe, expect, it, vi } from 'vitest'
import { createProjectService } from './projects'

const PID = 'prj_0123456789abcdef'

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn(async () => new Response(JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fn)
  return fn
}

function lastCall(fn: ReturnType<typeof mockFetch>) {
  const [url, init] = fn.mock.calls[fn.mock.calls.length - 1] as unknown as [string, RequestInit]
  return { url, init }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('projects service', () => {
  it('lists projects from the backend and rejects an unexpected shape', async () => {
    mockFetch(200, { count: 1, projects: [{ project_id: PID, name: 'A' }] })
    const result = await createProjectService().listProjects()
    expect(result.state === 'ok' && result.data[0].project_id).toBe(PID)

    mockFetch(200, { projects: 'nope' })
    expect((await createProjectService().listProjects()).state).toBe('error')
  })

  it('creates a project with only a name and an optional intent', async () => {
    const fn = mockFetch(201, { project_id: PID, name: 'A' })
    await createProjectService().createProject({ name: 'A', intent: { statement: 'reward >= 1' } })
    const { url, init } = lastCall(fn)
    expect(url).toBe('/api/v1/projects')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      name: 'A',
      intent: { statement: 'reward >= 1' },
    })
  })

  it('renames with PATCH and deletes with the confirmation name', async () => {
    const fn = mockFetch(200, { project_id: PID, name: 'B' })
    await createProjectService().updateProject(PID, { name: 'B' })
    expect(lastCall(fn).init.method).toBe('PATCH')

    const del = mockFetch(200, { status: 'deleted' })
    const result = await createProjectService().deleteProject(PID, 'B')
    expect(lastCall(del).init.method).toBe('DELETE')
    expect(JSON.parse(lastCall(del).init.body as string)).toEqual({ confirm_name: 'B' })
    expect(result.state).toBe('ok')
  })

  it('maps backend failures to stable, generic errors', async () => {
    mockFetch(404, { detail: { error: { message: 'internal secret' } } })
    const missing = await createProjectService().getProject(PID)
    expect(missing).toMatchObject({ state: 'error', error: { kind: 'not_found' } })
    expect(JSON.stringify(missing)).not.toContain('secret')

    mockFetch(409, {})
    expect(await createProjectService().deleteProject(PID, 'x')).toMatchObject({
      error: { kind: 'conflict' },
    })
  })

  it('uploads a document as the raw body with its filename', async () => {
    const fn = mockFetch(201, { duplicate: false, document: { document_id: 'doc_1' } })
    const file = new File(['# goals'], 'README.md', { type: 'text/markdown' })
    const result = await createProjectService().uploadDocument(PID, file)
    const { url, init } = lastCall(fn)
    expect(url).toBe(`/api/v1/projects/${PID}/documents?filename=README.md`)
    expect(init.body).toBe(file)
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('text/markdown')
    expect(result.state).toBe('ok')

    mockFetch(422, {})
    expect(await createProjectService().uploadDocument(PID, file)).toMatchObject({
      error: { kind: 'invalid_request' },
    })
  })

  it('reports an unreachable backend without inventing data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Promise.reject(new TypeError('failed'))),
    )
    expect(await createProjectService().listProjects()).toMatchObject({
      state: 'error',
      error: { kind: 'network' },
    })
  })

  it('verifies against a run and distinguishes waiting from evaluated', async () => {
    const fn = mockFetch(202, { state: 'waiting_for_evidence', verification: null, skipped: {} })
    const waiting = await createProjectService().verify(PID, { run_id: 'ses_00000001_r1' })
    expect(waiting.state === 'ok' && waiting.data.state).toBe('waiting_for_evidence')
    expect(lastCall(fn).url).toBe(`/api/v1/projects/${PID}/verifications`)

    mockFetch(200, { state: 'something else' })
    expect((await createProjectService().verify(PID, { run_id: 'r' })).state).toBe('error')
  })
})
