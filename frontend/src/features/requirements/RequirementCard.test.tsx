import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ExtractedRequirementDraft } from '../../schemas/intent'
import { RequirementCard } from './RequirementCard'

function draft(overrides: Partial<ExtractedRequirementDraft> = {}): ExtractedRequirementDraft {
  return {
    requirement_id: 'req_mock_goal_reward',
    description: 'Goal reward must equal the confirmed value.',
    rule_type: 'expected_reward',
    parameters: { expected: 100 },
    tolerance: null,
    source: 'developer_confirmed',
    confirmed: null,
    environment_version: 'warehouse_v1',
    ...overrides,
  }
}

describe('RequirementCard', () => {
  it('shows the description, the rule summary, and the source authority', () => {
    render(<RequirementCard draft={draft()} />)

    expect(screen.getByText('Goal reward must equal the confirmed value.')).toBeInTheDocument()
    expect(screen.getByText('Rule: expected_reward (expected=100)')).toBeInTheDocument()
    expect(screen.getByText('Source: developer statement')).toBeInTheDocument()
    expect(screen.getByText('Scope: warehouse_v1')).toBeInTheDocument()
    expect(screen.getByText('Draft — awaiting review')).toBeInTheDocument()
  })

  it('labels inferred requirements as hypotheses', () => {
    render(<RequirementCard draft={draft({ source: 'code_inferred', requirement_id: null })} />)
    expect(screen.getByText('Source: inferred from code — hypothesis')).toBeInTheDocument()
  })

  it('offers per-card confirm and reject actions only for decidable drafts', () => {
    const onConfirm = vi.fn()
    const onReject = vi.fn()
    render(<RequirementCard draft={draft()} onConfirm={onConfirm} onReject={onReject} />)

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))
    expect(onConfirm).toHaveBeenCalledOnce()
    expect(onReject).toHaveBeenCalledOnce()
  })

  it('offers no actions while the requirement id is unassigned', () => {
    render(
      <RequirementCard
        draft={draft({ requirement_id: null })}
        onConfirm={() => undefined}
        onReject={() => undefined}
      />,
    )
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('stops duplicate submissions while a decision request is pending', () => {
    render(
      <RequirementCard
        draft={draft()}
        pending
        onConfirm={() => undefined}
        onReject={() => undefined}
      />,
    )
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled()
  })
})
