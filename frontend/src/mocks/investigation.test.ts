import { afterEach, describe, expect, it, vi } from 'vitest'
import { DEMO_INCIDENT_ID } from './verification'
import { mockInvestigationAdapter } from './investigation'

describe('mock investigation adapter', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    mockInvestigationAdapter.resetMockInvestigationState()
  })

  function enableMocks() {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
  }

  it('fails closed when mocks are disabled', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    await expect(mockInvestigationAdapter.getInvestigation(DEMO_INCIDENT_ID)).rejects.toThrow(/VITE_USE_MOCKS/)
    await expect(mockInvestigationAdapter.requestInvestigation(DEMO_INCIDENT_ID)).rejects.toThrow(/VITE_USE_MOCKS/)
  })

  it('starts with no investigation for the demo incident — none was run yet', async () => {
    enableMocks()
    expect(await mockInvestigationAdapter.getInvestigation(DEMO_INCIDENT_ID)).toBeNull()
  })

  it('records the demo investigation only after an explicit request', async () => {
    enableMocks()
    const result = await mockInvestigationAdapter.requestInvestigation(DEMO_INCIDENT_ID)
    expect(result.incident_id).toBe(DEMO_INCIDENT_ID)

    const fetched = await mockInvestigationAdapter.getInvestigation(DEMO_INCIDENT_ID)
    expect(fetched?.investigation_id).toBe(result.investigation_id)
  })

  it('keeps observed facts and model hypotheses as separate claims', async () => {
    enableMocks()
    await mockInvestigationAdapter.requestInvestigation(DEMO_INCIDENT_ID)
    const result = await mockInvestigationAdapter.getInvestigation(DEMO_INCIDENT_ID)
    expect(result?.facts.length).toBeGreaterThan(0)
    expect(result?.hypotheses.length).toBeGreaterThan(0)

    // Every hypothesis statement is phrased as a proposal, and confidence is
    // populated only where the fixture records a provider estimate.
    for (const hypothesis of [...(result?.hypotheses ?? []), ...(result?.alternatives ?? [])]) {
      expect(hypothesis.statement.toLowerCase()).not.toMatch(/^confirmed\b/)
    }
    const firstHypothesis = result?.hypotheses[0]
    expect(firstHypothesis?.confidence).not.toBeNull()
    expect(result?.alternatives[0]?.confidence).toBeNull()
  })

  it('attaches a suggested action with confirmation flagged and provider metadata with no invented model', async () => {
    enableMocks()
    await mockInvestigationAdapter.requestInvestigation(DEMO_INCIDENT_ID)
    const result = await mockInvestigationAdapter.getInvestigation(DEMO_INCIDENT_ID)
    expect(result?.suggested_action?.requires_confirmation).toBe(true)
    expect(result?.provider?.provider).toBe('meta_model_api')
    // Model identity is unknown in the fixture; it must stay null, never a name.
    expect(result?.provider?.model).toBeNull()
    expect(result?.missing_evidence.length).toBeGreaterThan(0)
    expect(result?.limitations.length).toBeGreaterThan(0)
  })

  it('refuses to fabricate an investigation for unknown incident ids', async () => {
    enableMocks()
    expect(await mockInvestigationAdapter.getInvestigation('inc_unknown')).toBeNull()
    await expect(mockInvestigationAdapter.requestInvestigation('inc_unknown')).rejects.toThrow(/No demo investigation/)
  })
})
