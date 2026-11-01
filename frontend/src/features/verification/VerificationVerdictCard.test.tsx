import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { CheckStatus, VerificationCheckResult } from '../../schemas/verification'
import { formatCheckValue } from './checkValues'
import { VerificationVerdictCard } from './VerificationVerdictCard'

function check(overrides: Partial<VerificationCheckResult> = {}): VerificationCheckResult {
  return {
    requirement_id: 'req_demo_goal_reward',
    status: 'fail',
    expected: 100,
    actual: 40,
    tolerance: null,
    evidence_refs: ['evt_demo_step_812'],
    details: null,
    is_mandatory: true,
    timestamp: null,
    ...overrides,
  }
}

describe('formatCheckValue', () => {
  it('renders primitives directly and unavailable values as an explicit dash', () => {
    expect(formatCheckValue(100)).toBe('100')
    expect(formatCheckValue('warehouse_v1')).toBe('warehouse_v1')
    expect(formatCheckValue(false)).toBe('false')
    expect(formatCheckValue(null)).toBe('—')
    expect(formatCheckValue(undefined)).toBe('—')
    expect(formatCheckValue({ expected: 100 })).toBe('{"expected":100}')
    expect(formatCheckValue(Symbol('x'))).toBe('—')
  })
})

describe('VerificationVerdictCard', () => {
  it('shows an explicit deterministic mismatch on fail, never softened', () => {
    render(<VerificationVerdictCard result={check()} />)

    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('100')).toBeInTheDocument()
    expect(screen.getByText('40')).toBeInTheDocument()
    expect(screen.getByText('Mandatory check')).toBeInTheDocument()
  })

  it('labels a pass without overstating it', () => {
    render(
      <VerificationVerdictCard
        result={check({ status: 'pass', expected: 100, actual: 100, evidence_refs: [] })}
      />,
    )
    expect(screen.getByText('Passed')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it.each(['unknown', 'blocked', 'error', 'pending'] as const satisfies readonly CheckStatus[])(
    'renders %s as an inability to judge, not a pass or violation',
    (status) => {
      render(
        <VerificationVerdictCard
          result={check({ status, expected: null, actual: null, evidence_refs: [] })}
        />,
      )
      expect(screen.queryByText('Passed')).not.toBeInTheDocument()
      expect(screen.queryByText('Failed')).not.toBeInTheDocument()
    },
  )

  it('explains not-evaluable checks instead of inventing an outcome', () => {
    render(<VerificationVerdictCard result={check({ status: 'unknown', evidence_refs: [] })} />)
    expect(screen.getByText('Not evaluable')).toBeInTheDocument()
    expect(
      screen.getByText(
        'No applicable expectation is recorded for this requirement in the current scope, so no pass/fail claim is made.',
      ),
    ).toBeInTheDocument()
  })

  it('renders evidence refs as inert text without a navigation handler', () => {
    render(<VerificationVerdictCard result={check()} />)
    expect(screen.getByText('evt_demo_step_812').tagName).toBe('CODE')
    expect(screen.queryByRole('button', { name: 'evt_demo_step_812' })).not.toBeInTheDocument()
  })

  it('navigates to evidence only through the explicit handler', () => {
    const onOpenEvidence = vi.fn()
    render(
      <VerificationVerdictCard
        result={check({ evidence_refs: ['evt_1', 'evt_2'] })}
        onOpenEvidence={onOpenEvidence}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'evt_2' }))
    expect(onOpenEvidence).toHaveBeenCalledOnce()
    expect(onOpenEvidence).toHaveBeenCalledWith('evt_2')
  })

  it('shows tolerance and the advisory flag for non-mandatory checks', () => {
    render(
      <VerificationVerdictCard
        result={check({
          requirement_id: 'req_demo_step_penalty',
          status: 'pass',
          expected: -1,
          actual: -1,
          tolerance: 2,
          is_mandatory: false,
        })}
      />,
    )
    expect(screen.getByText('±2')).toBeInTheDocument()
    expect(screen.getByText('Advisory check')).toBeInTheDocument()
  })
})
