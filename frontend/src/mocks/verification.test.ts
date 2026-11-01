import { afterEach, describe, expect, it, vi } from 'vitest'
import { DEMO_INCIDENT_ID, DEMO_RUN_ID, mockVerificationAdapter } from './verification'

describe('mock verification adapter', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  function enableMocks() {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
  }

  it('fails closed when mocks are disabled', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    await expect(mockVerificationAdapter.getIncident(DEMO_INCIDENT_ID)).rejects.toThrow(
      /VITE_USE_MOCKS/,
    )
    await expect(mockVerificationAdapter.getVerificationResult(DEMO_INCIDENT_ID)).rejects.toThrow(
      /VITE_USE_MOCKS/,
    )
    await expect(mockVerificationAdapter.listEvidence(DEMO_INCIDENT_ID)).rejects.toThrow(
      /VITE_USE_MOCKS/,
    )
    await expect(mockVerificationAdapter.listAnomalies(DEMO_INCIDENT_ID)).rejects.toThrow(
      /VITE_USE_MOCKS/,
    )
  })

  it('serves the demo incident and verification result for the demo id', async () => {
    enableMocks()
    const incident = await mockVerificationAdapter.getIncident(DEMO_INCIDENT_ID)
    expect(incident).not.toBeNull()
    expect(incident?.run_id).toBe(DEMO_RUN_ID)
    expect(incident?.violation_type).toBe('reward_scale_mismatch')
    expect(incident?.detection_status).toBe('confirmed')
    expect(incident?.diagnosis_status).toBe('unresolved')

    const verification = await mockVerificationAdapter.getVerificationResult(DEMO_INCIDENT_ID)
    expect(verification?.overall_status).toBe('fail')
    const failed = verification?.results.find((r) => r.status === 'fail')
    expect(failed?.expected).toBe(100)
    expect(failed?.actual).toBe(40)
    expect(failed?.is_mandatory).toBe(true)
    // The scope with no applicable expectation stays honestly `unknown`.
    expect(verification?.results.some((r) => r.status === 'unknown')).toBe(true)
  })

  it('serves evidence references resolvable from the verification result', async () => {
    enableMocks()
    const verification = await mockVerificationAdapter.getVerificationResult(DEMO_INCIDENT_ID)
    const evidence = await mockVerificationAdapter.listEvidence(DEMO_INCIDENT_ID)
    const ids = new Set(evidence.map((e) => e.id))
    for (const ref of verification?.evidence_refs ?? []) {
      expect(ids.has(ref)).toBe(true)
    }
    expect(evidence.every((e) => e.run_identifier === DEMO_RUN_ID)).toBe(true)
  })

  it('serves anomaly observations distinct from the deterministic results', async () => {
    enableMocks()
    const anomalies = await mockVerificationAdapter.listAnomalies(DEMO_INCIDENT_ID)
    expect(anomalies).toHaveLength(1)
    expect(anomalies[0]?.anomaly_type).toBe('reward_deviation')
    expect(anomalies[0]?.score).not.toBeNull()
    expect(anomalies[0]?.threshold).not.toBeNull()
  })

  it('never serves fixtures for unknown incident ids', async () => {
    enableMocks()
    expect(await mockVerificationAdapter.getIncident('inc_unknown')).toBeNull()
    expect(await mockVerificationAdapter.getVerificationResult('inc_unknown')).toBeNull()
    expect(await mockVerificationAdapter.listEvidence('inc_unknown')).toEqual([])
    expect(await mockVerificationAdapter.listAnomalies('inc_unknown')).toEqual([])
  })
})
