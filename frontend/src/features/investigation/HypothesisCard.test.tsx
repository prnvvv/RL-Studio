import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { InvestigationHypothesis } from '../../schemas/investigation'
import { HypothesisCard } from './HypothesisCard'

function hypothesis(overrides: Partial<InvestigationHypothesis> = {}): InvestigationHypothesis {
  return {
    hypothesis_id: 'hyp_demo_reward_scale_change',
    statement:
      'The environment goal-reward scale changed during the recorded fault-injection interval.',
    reasoning:
      'Only goal-reward observations diverge while step-penalty checks stay within tolerance.',
    supporting_evidence_refs: ['evt_demo_step_812'],
    confidence: 0.72,
    ...overrides,
  }
}

describe('HypothesisCard', () => {
  it('labels the statement as a hypothesis, never a confirmed cause', () => {
    render(<HypothesisCard hypothesis={hypothesis()} />)
    expect(screen.getByText('Hypothesis')).toBeInTheDocument()
    expect(screen.queryByText(/Confirmed|Root cause/)).not.toBeInTheDocument()
    expect(screen.getByText(/The environment goal-reward scale changed/)).toBeInTheDocument()
    expect(screen.getByText(/Only goal-reward observations diverge/)).toBeInTheDocument()
  })

  it('labels alternatives distinctly from primary hypotheses', () => {
    render(<HypothesisCard hypothesis={hypothesis()} isAlternative />)
    expect(screen.getByText('Alternative explanation')).toBeInTheDocument()
  })

  it('shows confidence only when the record supplies it, labelled as an unverified estimate', () => {
    const first = render(<HypothesisCard hypothesis={hypothesis()} />)
    expect(screen.getByText('Confidence (provider estimate, unverified): 0.72')).toBeInTheDocument()
    first.unmount()

    render(<HypothesisCard hypothesis={hypothesis({ confidence: null })} />)
    expect(screen.queryByText(/Confidence/)).not.toBeInTheDocument()
  })

  it('renders supporting evidence as inert refs without a navigation handler', () => {
    render(<HypothesisCard hypothesis={hypothesis()} />)
    expect(screen.getByText('evt_demo_step_812').tagName).toBe('CODE')
    expect(screen.queryByRole('button', { name: 'evt_demo_step_812' })).not.toBeInTheDocument()
  })

  it('navigates to supporting evidence only through the explicit handler', () => {
    const onOpenEvidence = vi.fn()
    render(<HypothesisCard hypothesis={hypothesis()} onOpenEvidence={onOpenEvidence} />)
    fireEvent.click(screen.getByRole('button', { name: 'evt_demo_step_812' }))
    expect(onOpenEvidence).toHaveBeenCalledOnce()
    expect(onOpenEvidence).toHaveBeenCalledWith('evt_demo_step_812')
  })

  it('warns that a hypothesis cannot authorise recovery even with confidence shown', () => {
    render(<HypothesisCard hypothesis={hypothesis()} />)
    expect(
      screen.getByText(/does not establish cause and cannot authorise any recovery action/),
    ).toBeInTheDocument()
  })
})
