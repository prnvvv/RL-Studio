import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createRecoveryService,
  recoveryAssessmentItemPath,
  recoveryAssessmentPath,
  recoveryItemPath,
  recoveryPath,
} from './recovery'
import { buildRequestUrl } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const ASSESSMENT_BODY = {
  incident_id: 'inc_demo',
  recovery_assessment_id: 'assess_1',
  recovery_eligibility: 'eligible',
  recovery_strategy: 'restore_checkpoint',
  recovery_reason: null,
  source_checkpoint_id: 'ckpt_pre_impact',
  target_environment_version: 'warehouse_v1',
  target_agent_config_fingerprint: null,
  compatibility: [
    { name: 'checkpoint exists', outcome: 'pass', detail: 'Hash verified.', evidence_ids: [] },
    { name: 'environment compatible', outcome: 'pass', detail: 'Same version.', evidence_ids: [] },
  ],
  lineage_gaps: [],
  evidence_ids: [],
  warnings: [],
  errors: [],
  details: {},
  created_at: '2026-11-02T00:00:00Z',
}

const RECOVERY_BODY = {
  recovery_id: 'rec_1',
  incident_id: 'inc_demo',
  assessment_id: 'assess_1',
  recovery_status: 'completed',
  recovery_strategy: 'restore_checkpoint',
  recovery_reason: null,
  source_checkpoint_id: 'ckpt_pre_impact',
  recovery_artifact_id: null,
  recovered_checkpoint_id: 'ckpt_recovered',
  target_environment_version: 'warehouse_v1',
  target_agent_config_fingerprint: null,
  recovery_started_at: '2026-11-02T00:01:00Z',
  recovery_completed_at: '2026-11-02T00:02:00Z',
  proposed_actions: [],
  executed_actions: [
    {
      action: 'restore_checkpoint',
      status: 'completed',
      detail: null,
      started_at: null,
      completed_at: null,
    },
  ],
  preflight: {},
  failure_reason: null,
  evidence_ids: [],
  warnings: [],
  errors: [],
  details: {},
  created_at: '2026-11-02T00:00:30Z',
  updated_at: '2026-11-02T00:02:00Z',
}

describe('planned request paths', () => {
  it('encodes ids into the recovery paths', () => {
    expect(buildRequestUrl('http://localhost:8000', recoveryAssessmentPath('inc/1'))).toBe(
      'http://localhost:8000/api/v1/incidents/inc%2F1/recovery-assessments',
    )
    expect(
      buildRequestUrl('http://localhost:8000', recoveryAssessmentItemPath('inc/1', 'a/2')),
    ).toBe('http://localhost:8000/api/v1/incidents/inc%2F1/recovery-assessments/a%2F2')
    expect(buildRequestUrl('http://localhost:8000', recoveryPath('inc/1'))).toBe(
      'http://localhost:8000/api/v1/incidents/inc%2F1/recoveries',
    )
    expect(buildRequestUrl('http://localhost:8000', recoveryItemPath('inc/1', 'r/3'))).toBe(
      'http://localhost:8000/api/v1/incidents/inc%2F1/recoveries/r%2F3',
    )
  })
})

describe('recovery service', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const service = createRecoveryService()

  it('posts assessment requests with the exact request payload', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, ASSESSMENT_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const request = {
      recovery_strategy: 'restore_checkpoint',
      source_checkpoint_id: 'ckpt_pre_impact',
      target_environment_version: 'warehouse_v1',
      discard_pending_rollouts: true,
      collect_fresh_experience: true,
      idempotency_key: 'assess-key-1',
    } as const

    const result = await service.createAssessment('inc_demo', request)

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/incidents/inc_demo/recovery-assessments')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual(request)
    expect(result.state).toBe('ok')
    if (result.state === 'ok') {
      expect(result.data.recovery_eligibility).toBe('eligible')
      expect(result.data.compatibility).toHaveLength(2)
    }
  })

  it('posts execution requests including execute:true and the approval mark', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, RECOVERY_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const request = {
      assessment_id: 'assess_1',
      execute: true,
      approval: { approved: true, approved_by: 'developer', approved_at: '2026-11-02T00:00:59Z' },
      idempotency_key: 'recover-key-1',
    } as const

    const result = await service.createRecovery('inc_demo', request)

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/incidents/inc_demo/recoveries')
    expect(JSON.parse(init.body as string)).toEqual(request)
    expect(result.state).toBe('ok')
    if (result.state === 'ok') {
      // The record separates the executed step from its evaluation lifecycle.
      expect(result.data.recovery_status).toBe('completed')
      expect(result.data.executed_actions).not.toHaveLength(0)
      expect(result.data.failure_reason).toBeNull()
    }
  })

  it('surfaces conflicts as the stable conflict error kind without retrying', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(409, { detail: 'Conflict' }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await service.createRecovery('inc_demo', { execute: true })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(result.state).toBe('error')
    if (result.state === 'error') expect(result.error.kind).toBe('conflict')
  })
})
