import { afterEach, describe, expect, it, vi } from 'vitest'
import { createInvestigationService, investigationPath } from './investigation'
import { buildRequestUrl } from './client'
import { DEMO_INCIDENT_ID } from '../mocks/verification'
import { MOCK_DATA_LABEL } from '../mocks'
import { mockInvestigationAdapter } from '../mocks/investigation'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('planned request path', () => {
  it('encodes the incident id into the investigation path', () => {
    expect(buildRequestUrl('http://localhost:8000', investigationPath('inc/one'))).toBe(
      'http://localhost:8000/api/v1/incidents/inc%2Fone/investigation',
    )
  })
})

describe('real adapter (mocks disabled)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('fetches and requests investigations on the planned endpoint', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    const fetchMock = vi.fn(async () => jsonResponse(200, { investigation_id: 'inv_1', incident_id: DEMO_INCIDENT_ID }))
    vi.stubGlobal('fetch', fetchMock)
    const service = createInvestigationService()

    const result = await service.getInvestigation(DEMO_INCIDENT_ID)
    const [getUrl, getInit] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(getUrl).toBe(`/api/v1/incidents/${DEMO_INCIDENT_ID}/investigation`)
    expect(getInit.method).toBe('GET')
    expect(result.state).toBe('ok')

    const requested = await service.requestInvestigation(DEMO_INCIDENT_ID)
    const [postUrl, postInit] = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect(postUrl).toBe(`/api/v1/incidents/${DEMO_INCIDENT_ID}/investigation`)
    expect(postInit.method).toBe('POST')
    expect(requested.state).toBe('ok')
  })

  it('returns honest not_found / service errors until the endpoint exists', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(503, { detail: 'Service Unavailable' })))
    const service = createInvestigationService()

    const fetched = await service.getInvestigation(DEMO_INCIDENT_ID)
    expect(fetched.state).toBe('error')
    if (fetched.state === 'error') expect(fetched.error.kind).toBe('unavailable')

    const requested = await service.requestInvestigation(DEMO_INCIDENT_ID)
    expect(requested.state).toBe('error')
    if (requested.state === 'error') expect(requested.error.kind).toBe('unavailable')
  })
})

describe('mock adapter (VITE_USE_MOCKS=true)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    mockInvestigationAdapter.resetMockInvestigationState()
  })

  it('starts with no investigation — none has run yet — and stays not labeled', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    const service = createInvestigationService()
    const before = await service.getInvestigation(DEMO_INCIDENT_ID)
    expect(before.state).toBe('error')
    if (before.state === 'error') expect(before.error.kind).toBe('not_found')
  })

  it('records a labeled sample investigation after an explicit request', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    const service = createInvestigationService()

    const requested = await service.requestInvestigation(DEMO_INCIDENT_ID)
    expect(requested.state).toBe('ok')
    if (requested.state === 'ok' && 'label' in requested.data) {
      expect(requested.data.label).toBe(MOCK_DATA_LABEL)
      // Facts and hypotheses remain separate claims behind the label too.
      expect(requested.data.data.facts.length).toBeGreaterThan(0)
      expect(requested.data.data.hypotheses.length).toBeGreaterThan(0)
      const withConfidence = requested.data.data.hypotheses.filter((h) => h.confidence !== null)
      for (const hypothesis of withConfidence) {
        expect(hypothesis.confidence ?? null).not.toBeNull()
      }
    }

    const fetched = await service.getInvestigation(DEMO_INCIDENT_ID)
    expect(fetched.state).toBe('ok')
  })

  it('does not fabricate an investigation for unknown incident ids', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    const service = createInvestigationService()

    const fetched = await service.getInvestigation('inc_unknown')
    expect(fetched.state).toBe('error')
    if (fetched.state === 'error') expect(fetched.error.kind).toBe('not_found')

    const requested = await service.requestInvestigation('inc_unknown')
    expect(requested.state).toBe('error')
    if (requested.state === 'error') expect(requested.error.kind).toBe('not_found')
  })
})
