import { afterEach, describe, expect, it, vi } from 'vitest'
import { MOCK_DATA_LABEL } from './index'
import { mockIntentRequirementsAdapter, resetMockIntentState } from './intentRequirements'

describe('mock intent adapter', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    resetMockIntentState()
  })

  function enable() {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
  }

  it('fails closed when mocks are disabled', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    await expect(mockIntentRequirementsAdapter.submitIntent('The goal reward must be 100.')).rejects.toThrow(
      /VITE_USE_MOCKS/,
    )
  })

  it('labels every payload as sample data', async () => {
    enable()
    const submission = await mockIntentRequirementsAdapter.submitIntent('The goal reward must be 100.')
    expect(submission.label).toBe(MOCK_DATA_LABEL)
  })

  it('extracts an accepted reward requirement', async () => {
    enable()
    const { data } = await mockIntentRequirementsAdapter.submitIntent('The goal reward must be 100.')
    expect(data.extraction_status).toBe('accepted')
    expect(data.warnings).toEqual([])
    expect(data.requirements).toHaveLength(1)
    expect(data.requirements[0].rule_type).toBe('expected_reward')
    expect(data.requirements[0].source).toBe('developer_confirmed')
    expect(data.requirements[0].confirmed).toBeNull()
  })

  it('reports ambiguous when the domain matches but no value is asserted', async () => {
    enable()
    const { data } = await mockIntentRequirementsAdapter.submitIntent('Observation handling and the goal reward.')
    expect(data.extraction_status).toBe('ambiguous')
    expect(data.warnings.length).toBeGreaterThan(0)
    expect(data.requirements).toEqual([])
  })

  it('reports unsupported statements outside the domain without fabricating', async () => {
    enable()
    const { data } = await mockIntentRequirementsAdapter.submitIntent('Render the vision model faster.')
    expect(data.extraction_status).toBe('unsupported')
    expect(data.warnings.length).toBeGreaterThan(0)
    expect(data.requirements).toEqual([])
  })

  it('extracts observation and termination statements within the domain', async () => {
    enable()
    const { data } = await mockIntentRequirementsAdapter.submitIntent(
      'Observations must be intact and termination must be recorded.',
    )
    expect(data.extraction_status).toBe('accepted')
    const ruleTypes = data.requirements.map((requirement) => requirement.rule_type)
    expect(ruleTypes).toContain('observation_fidelity')
    expect(ruleTypes).toContain('termination_validity')
  })

  it('returns a confirmed or rejected record only for known demo drafts', async () => {
    enable()
    const confirmed = await mockIntentRequirementsAdapter.decideRequirement('req_mock_goal_reward', 'confirm')
    expect(confirmed.data.requirement_id).toBe('req_mock_goal_reward')
    expect(confirmed.data.confirmed).toBe(true)
    expect(confirmed.data.confirmed).not.toBeNull()

    const rejected = await mockIntentRequirementsAdapter.decideRequirement('req_mock_step_penalty', 'reject')
    expect(rejected.data.confirmed).toBe(false)

    await expect(mockIntentRequirementsAdapter.decideRequirement('req_unknown', 'confirm')).rejects.toThrow(
      /holds no draft/,
    )
  })

  it('lists only decided requirements this session; empty is honest', async () => {
    enable()
    const before = await mockIntentRequirementsAdapter.listRequirements()
    expect(before.data).toEqual([])

    await mockIntentRequirementsAdapter.decideRequirement('req_mock_observation', 'confirm')
    const after = await mockIntentRequirementsAdapter.listRequirements()
    expect(after.data).toHaveLength(1)
    expect(after.data[0].requirement_id).toBe('req_mock_observation')
    expect(after.data[0].confirmed).toBe(true)
    expect(after.data[0].source_version).toBe('mock-adapter@1.0')
  })
})
