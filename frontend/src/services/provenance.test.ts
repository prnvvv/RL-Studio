import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  artifactPath,
  createProvenanceService,
  incidentImpactPath,
  runArtifactsPath,
  runProvenancePath,
} from './provenance'
import { buildRequestUrl } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('planned request paths', () => {
  it('encodes ids into the provenance paths', () => {
    expect(buildRequestUrl('http://localhost:8000', runProvenancePath('run/one'))).toBe(
      'http://localhost:8000/api/v1/runs/run%2Fone/provenance',
    )
    expect(buildRequestUrl('http://localhost:8000', runArtifactsPath('run/one'))).toBe(
      'http://localhost:8000/api/v1/runs/run%2Fone/artifacts',
    )
    expect(buildRequestUrl('http://localhost:8000', artifactPath('a/1'))).toBe(
      'http://localhost:8000/api/v1/artifacts/a%2F1',
    )
    expect(buildRequestUrl('http://localhost:8000', incidentImpactPath('inc/1'))).toBe(
      'http://localhost:8000/api/v1/incidents/inc%2F1/impact',
    )
  })
})

describe('provenance service', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const service = createProvenanceService()

  it('fetches the recorded provenance trace from the live endpoint', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, {
        provenance_id: 'prov_demo',
        run_id: 'run_demo',
        provenance_status: 'complete',
        lineage_completeness: 'complete',
        artifact_count: 0,
        artifacts: [],
        links: [],
        warnings: [],
        evidence_ids: [],
        details: {},
        created_at: '2026-11-02T00:00:00Z',
        updated_at: '2026-11-02T00:00:00Z',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await service.getRunProvenance('run_demo')

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/runs/run_demo/provenance')
    expect(init.method).toBe('GET')
    expect(result.state).toBe('ok')
    if (result.state === 'ok') {
      expect(result.data.provenance_status).toBe('complete')
    }
  })

  it('keeps an unknown-impact analysis untouched rather than reclassifying it', async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, {
        impact_id: 'impact_demo',
        incident_id: 'inc_demo',
        run_id: 'run_demo',
        impact_status: 'unknown_incomplete_lineage',
        impact_score: null,
        source_environment_version: 'warehouse_v1',
        corruption_start_timestep: null,
        corruption_end_timestep: null,
        affected_artifact_ids: [],
        affected_trajectory_ids: [],
        affected_policy_update_ids: [],
        affected_checkpoint_ids: [],
        evidence_ids: [],
        warnings: ['Lineage incomplete before the corruption window.'],
        errors: [],
        details: {},
        created_at: '2026-11-02T00:00:00Z',
        completed_at: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await service.getIncidentImpact('inc_demo')

    expect(result.state).toBe('ok')
    if (result.state === 'ok') {
      // The service preserves the four-way classification verbatim.
      expect(result.data.impact_status).toBe('unknown_incomplete_lineage')
      expect(result.data.completed_at).toBeNull()
    }
  })

  it('returns honest errors instead of throwing for missing records', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(404, { detail: 'Not Found' })),
    )
    const result = await service.getArtifact('ckpt_missing')
    expect(result.state).toBe('error')
    if (result.state === 'error') {
      expect(result.error.kind).toBe('not_found')
    }
  })
})
