import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSimulationService, runSimulationPath } from './simulation'
import { buildRequestUrl } from './client'
import { DEMO_RUN_ID } from '../mocks/verification'
import { MOCK_DATA_LABEL } from '../mocks'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('planned request path', () => {
  it('encodes the run id into the simulation path', () => {
    expect(buildRequestUrl('http://localhost:8000', runSimulationPath('run/one'))).toBe(
      'http://localhost:8000/api/v1/runs/run%2Fone/simulation',
    )
  })
})

describe('real adapter (mocks disabled)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('fetches the recorded replay from the planned endpoint', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { run_id: DEMO_RUN_ID, schema_version: '1.0' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const service = createSimulationService()
    const result = await service.getRunSimulation(DEMO_RUN_ID)

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe(`/api/v1/runs/${DEMO_RUN_ID}/simulation`)
    expect(init.method).toBe('GET')
    expect(result.state).toBe('ok')
  })

  it('returns honest not_found / unavailable until the endpoint exists', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(404, { detail: 'Not Found' })),
    )
    const service = createSimulationService()

    const result = await service.getRunSimulation(DEMO_RUN_ID)
    expect(result.state).toBe('error')
    if (result.state === 'error') expect(result.error.kind).toBe('not_found')
  })
})

describe('mock adapter (VITE_USE_MOCKS=true)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('returns the demo replay labeled as sample data without touching the network', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    const service = createSimulationService()
    const result = await service.getRunSimulation(DEMO_RUN_ID)
    expect(result.state).toBe('ok')
    if (result.state === 'ok' && 'label' in result.data) {
      expect(result.data.label).toBe(MOCK_DATA_LABEL)
      expect(result.data.data.environment.run_id).toBe(DEMO_RUN_ID)
    }
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('maps unknown run ids to stable not_found even in mock mode', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    const service = createSimulationService()

    const result = await service.getRunSimulation('run_unknown')
    expect(result.state).toBe('error')
    if (result.state === 'error') expect(result.error.kind).toBe('not_found')
  })
})
