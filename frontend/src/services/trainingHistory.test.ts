import { afterEach, describe, expect, it, vi } from 'vitest'
import { createTrainingHistoryService } from './trainingHistory'
import { PROJECT_A, installHistoryFake, makeRun } from '../test/trainingHistoryFake'

afterEach(() => vi.unstubAllGlobals())

describe('training history service', () => {
  it('sends filters, search, sort and paging to the backend and omits empty ones', async () => {
    const spy = installHistoryFake({ runs: [makeRun({ run_id: 'ses_00000001_r1' })] })
    await createTrainingHistoryService().listRuns(PROJECT_A, {
      agentId: 'agt_000000000001',
      status: 'stopped',
      q: '  ppo  ',
      sort: 'oldest',
      limit: 10,
      offset: 20,
      experimentId: '',
    })
    const url = new URL(String(spy.mock.calls[0][0]), 'http://x')
    expect(url.pathname).toBe(`/api/v1/projects/${PROJECT_A}/training-runs`)
    expect(Object.fromEntries(url.searchParams)).toEqual({
      agent_id: 'agt_000000000001',
      status: 'stopped',
      q: 'ppo',
      sort: 'oldest',
      limit: '10',
      offset: '20',
    })
  })

  it('maps a run that is missing or belongs to another project to not_found', async () => {
    installHistoryFake({
      runs: [makeRun({ run_id: 'ses_00000001_r1', project_id: 'prj_bbbbbbbbbbbbbbbb' })],
    })
    const result = await createTrainingHistoryService().getRun(PROJECT_A, 'ses_00000001_r1')
    expect(result).toMatchObject({ state: 'error', error: { kind: 'not_found' } })
  })

  it('treats a malformed list as unexpected instead of inventing runs', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ items: [{ nope: 1 }], total: 1 }), { status: 200 }),
      ),
    )
    const result = await createTrainingHistoryService().listRuns(PROJECT_A)
    expect(result).toMatchObject({ state: 'error', error: { kind: 'unexpected' } })
  })

  it('reports an unreachable backend as a network error, never as an empty history', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('failed')
      }),
    )
    expect(await createTrainingHistoryService().listRuns(PROJECT_A)).toMatchObject({
      state: 'error',
      error: { kind: 'network' },
    })
  })

  it('returns a null latest run for an empty project', async () => {
    installHistoryFake({ runs: [] })
    expect(await createTrainingHistoryService().latestRun(PROJECT_A)).toEqual({
      state: 'ok',
      data: null,
    })
  })
})
