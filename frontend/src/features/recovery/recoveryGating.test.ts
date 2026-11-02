import { describe, expect, it } from 'vitest'
import type {
  Recovery,
  RecoveryAssessment,
  RecoveryCompatibilityCheck,
} from '../../schemas/recovery'
import {
  assessmentGate,
  recoveryOutcomeClaim,
  recoveryPresentation,
  strategyLabel,
} from './recoveryGating'

function check(
  name: string,
  outcome: RecoveryCompatibilityCheck['outcome'],
): RecoveryCompatibilityCheck {
  return { name, outcome, detail: 'recorded detail', evidence_ids: [] }
}

const BASE_ASSESSMENT: RecoveryAssessment = {
  recovery_assessment_id: 'assess_1',
  incident_id: 'inc_demo',
  recovery_eligibility: 'eligible',
  recovery_strategy: 'restore_checkpoint',
  recovery_reason: null,
  source_checkpoint_id: 'ckpt_pre',
  target_environment_version: 'warehouse_v1',
  target_agent_config_fingerprint: null,
  compatibility: [check('checkpoint exists', 'pass'), check('environment compatible', 'pass')],
  lineage_gaps: [],
  evidence_ids: [],
  warnings: [],
  errors: [],
  details: {},
  created_at: '2026-11-02T00:00:00Z',
}

function assessment(overrides: Partial<RecoveryAssessment> = {}): RecoveryAssessment {
  return { ...BASE_ASSESSMENT, ...overrides }
}

describe('assessmentGate', () => {
  it('opens the gate only for eligible assessments whose checks all passed', () => {
    const gate = assessmentGate(BASE_ASSESSMENT)
    expect(gate.canRequestExecution).toBe(true)
    expect(gate.allChecksPassed).toBe(true)
  })

  it('keeps the gate closed when no assessment exists', () => {
    const gate = assessmentGate(null)
    expect(gate.canRequestExecution).toBe(false)
    expect(gate.allChecksPassed).toBe(false)
    expect(gate.reason).toMatch(/no recorded assessment/i)
  })

  it('treats ineligible, unknown, and needs_review eligibility as closed gates', () => {
    for (const eligibility of ['ineligible', 'unknown', 'needs_review'] as const) {
      const gate = assessmentGate(assessment({ recovery_eligibility: eligibility }))
      expect(gate.canRequestExecution).toBe(false)
      expect(gate.allChecksPassed).toBe(false)
    }
  })

  it('never softens non-pass check outcomes into passes', () => {
    for (const outcome of ['fail', 'unknown', 'blocked', 'skipped'] as const) {
      const gate = assessmentGate(
        assessment({ compatibility: [check('lineage verified', outcome)] }),
      )
      expect(gate.canRequestExecution).toBe(false)
      expect(gate.allChecksPassed).toBe(false)
    }
  })

  it('treats an empty compatibility list as closed, never as vacuously passed', () => {
    const gate = assessmentGate(assessment({ compatibility: [] }))
    expect(gate.canRequestExecution).toBe(false)
    expect(gate.reason).toMatch(/records no compatibility checks/i)
  })

  it('names the blocking check in the reason', () => {
    const gate = assessmentGate(
      assessment({
        compatibility: [check('checkpoint exists', 'pass'), check('hash integrity', 'fail')],
      }),
    )
    expect(gate.reason).toContain('hash integrity: fail')
  })
})

describe('recoveryPresentation', () => {
  const BASE: Omit<Recovery, 'recovery_status'> = {
    recovery_id: 'rec_1',
    incident_id: 'inc_demo',
    assessment_id: 'assess_1',
    recovery_strategy: 'restore_checkpoint',
    recovery_reason: null,
    source_checkpoint_id: 'ckpt_pre',
    recovery_artifact_id: null,
    recovered_checkpoint_id: 'ckpt_recovered',
    target_environment_version: 'warehouse_v1',
    target_agent_config_fingerprint: null,
    recovery_started_at: null,
    recovery_completed_at: null,
    proposed_actions: [],
    executed_actions: [],
    preflight: {},
    failure_reason: null,
    evidence_ids: [],
    warnings: [],
    errors: [],
    details: {},
    created_at: '2026-11-02T00:00:00Z',
    updated_at: '2026-11-02T00:01:00Z',
  }

  function recovery(status: Recovery['recovery_status']): Recovery {
    return { ...BASE, recovery_status: status }
  }

  it('keeps every lifecycle state visible as its own presentation', () => {
    expect(recoveryPresentation('proposed')).toBe('proposed')
    expect(recoveryPresentation('approved')).toBe('approved')
    expect(recoveryPresentation('executing')).toBe('executing')
    expect(recoveryPresentation('blocked')).toBe('blocked')
    expect(recoveryPresentation('cancelled')).toBe('cancelled')
    expect(recoveryPresentation('failed')).toBe('executed_failed')
    expect(recoveryPresentation('evaluated')).toBe('evaluated')
  })

  it('presents completed execution as execution, never as success', () => {
    const claim = recoveryOutcomeClaim(recovery('completed'))
    expect(claim.claim).toBe('executed')
    expect(claim.label).toMatch(/not established/i)
  })

  it('carries failure and blocked outcomes without invention', () => {
    expect(recoveryOutcomeClaim(recovery('failed')).claim).toBe('not_successful')
    expect(recoveryOutcomeClaim(recovery('blocked')).claim).toBe('unknown')
    expect(recoveryOutcomeClaim(recovery('proposed')).claim).toBe('unknown')
    expect(recoveryOutcomeClaim(recovery('evaluated')).claim).toBe('unknown')
  })

  it('labels allow-listed strategies only', () => {
    expect(strategyLabel('restore_checkpoint')).toBe('Restore checkpoint')
    expect(strategyLabel('continue_with_fresh_experience')).toBe('Continue with fresh experience')
  })
})
