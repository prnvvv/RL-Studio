import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createVerificationService,
  incidentAnomaliesPath,
  incidentEvidencePath,
  incidentPath,
  incidentVerificationPath,
} from './verification'
import { buildRequestUrl } from './client'
import { DEMO_INCIDENT_ID, DEMO_RUN_ID } from '../mocks/verification'
import { MOCK_DATA_LABEL } from '../mocks'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('planned request paths', () => {
  it('encodes the incident id and uses stable collection paths', () => {
    expect(buildRequestUrl('http://localhost:8000', incidentPath(DEMO_INCIDENT_ID))).toBe(
      `http://localhost:8000/api/v1/incidents/${DEMO_INCIDENT_ID}`,
    )
    expect(buildRequestUrl('', incidentVerificationPath('inc/one'))).toBe('/api/v1/incidents/inc%2Fone/verification')
    expect(buildRequestUrl('', incidentEvidencePath('inc/one'))).toBe('/api/v1/incidents/inc%2Fone/evidence')
    expect(buildRequestUrl('', incidentAnomaliesPath('inc/one'))).toBe('/api/v1/incidents/inc%2Fone/anomalies')
  })
})

describe('real adapter (mocks disabled)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('fetches incident and verification payloads from the planned endpoints', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { incident_id: DEMO_INCIDENT_ID, run_id: DEMO_RUN_ID }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const service = createVerificationService()
    const incident = await service.getIncident(DEMO_INCIDENT_ID)

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe(`/api/v1/incidents/${DEMO_INCIDENT_ID}`)
    expect(init.method).toBe('GET')
    expect(incident.state).toBe('ok')
    if (incident.state === 'ok' && 'incident_id' in incident.data) {
      expect(incident.data.run_id).toBe(DEMO_RUN_ID)
    }
  })

  it('returns honest not_found / unavailable until the planned endpoints exist', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, { detail: 'Not Found' })))
    const service = createVerificationService()

    for (const call of [
      service.getIncident(DEMO_INCIDENT_ID),
      service.getVerificationResult(DEMO_INCIDENT_ID),
      service.listEvidence(DEMO_INCIDENT_ID),
      service.listAnomalies(DEMO_INCIDENT_ID),
    ] as const) {
      const result = await call
      expect(result.state).toBe('error')
      if (result.state === 'error') expect(result.error.kind).toBe('not_found')
    }
  })
})

describe('mock adapter (VITE_USE_MOCKS=true)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('returns payloads labeled as sample data without touching the network', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)

    const service = createVerificationService()

    const incident = await service.getIncident(DEMO_INCIDENT_ID)
    expect(incident.state).toBe('ok')
    if (incident.state === 'ok' && 'label' in incident.data) {
      expect(incident.data.label).toBe(MOCK_DATA_LABEL)
      expect(incident.data.data.violation_type).toBe('reward_scale_mismatch')
    }

    const verification = await service.getVerificationResult(DEMO_INCIDENT_ID)
    expect(verification.state).toBe('ok')
    if (verification.state === 'ok' && 'label' in verification.data) {
      expect(verification.data.data.results.length).toBeGreaterThan(0)
    }

    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('serves labeled evidence and anomaly lists for the demo incident', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    const service = createVerificationService()

    const evidence = await service.listEvidence(DEMO_INCIDENT_ID)
    expect(evidence.state).toBe('ok')
    if (evidence.state === 'ok' && 'label' in evidence.data) {
      expect(evidence.data.data.length).toBeGreaterThan(0)
    }

    const anomalies = await service.listAnomalies(DEMO_INCIDENT_ID)
    expect(anomalies.state).toBe('ok')
    if (anomalies.state === 'ok' && 'label' in anomalies.data) {
      expect(anomalies.data.data[0]?.anomaly_type).toBe('reward_deviation')
    }
  })

  it('maps unknown incident ids to stable not_found even in mock mode', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    const service = createVerificationService()

    const incident = await service.getIncident('inc_unknown')
    expect(incident.state).toBe('error')
    if (incident.state === 'error') expect(incident.error.kind).toBe('not_found')

    const verification = await service.getVerificationResult('inc_unknown')
    expect(verification.state).toBe('error')
    if (verification.state === 'error') expect(verification.error.kind).toBe('not_found')
  })
})
