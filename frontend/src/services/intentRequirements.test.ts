import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  createIntentRequirementsService,
  INTENT_SUBMIT_PATH,
  REQUIREMENTS_LIST_PATH,
  requirementDecisionPath,
} from './intentRequirements'
import { buildRequestUrl } from './client'
import { MOCK_DATA_LABEL } from '../mocks'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('planned request paths', () => {
  it('encodes the requirement id and uses stable collection paths', () => {
    expect(buildRequestUrl('http://localhost:8000', INTENT_SUBMIT_PATH)).toBe(
      'http://localhost:8000/api/v1/intents',
    )
    expect(buildRequestUrl('', REQUIREMENTS_LIST_PATH)).toBe('/api/v1/requirements')
    expect(buildRequestUrl('', requirementDecisionPath('req/goal'))).toBe(
      '/api/v1/requirements/req%2Fgoal/review-decision',
    )
  })
})

describe('real adapter (mocks disabled)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
  })

  it('submits the schema-versioned payload to the planned endpoint', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, {
        schema_version: '1.0',
        extraction_status: 'accepted',
        warnings: [],
        requirements: [],
        timestamp: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const service = createIntentRequirementsService()
    const result = await service.submitIntent('The goal reward must be 100.')

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/intents')
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ schema_version: '1.0', text: 'The goal reward must be 100.' }))
    expect(result.state).toBe('ok')
  })

  it('returns honest not_found until the planned endpoints are implemented', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(404, { detail: 'Not Found' })))
    const service = createIntentRequirementsService()

    const submission = await service.submitIntent('text')
    expect(submission.state).toBe('error')
    if (submission.state === 'error') expect(submission.error.kind).toBe('not_found')

    const list = await service.listRequirements()
    expect(list.state).toBe('error')
    if (list.state === 'error') expect(list.error.kind).toBe('not_found')
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

    const service = createIntentRequirementsService()

    const submission = await service.submitIntent('The goal reward must be 100.')
    expect(submission.state).toBe('ok')
    if (submission.state === 'ok' && 'label' in submission.data) {
      expect(submission.data.label).toBe(MOCK_DATA_LABEL)
    }

    const decision = await service.decideRequirement('req_mock_goal_reward', 'confirm')
    expect(decision.state).toBe('ok')
    if (decision.state === 'ok' && 'label' in decision.data) {
      expect(decision.data.data.requirement_id).toBe('req_mock_goal_reward')
    }
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
