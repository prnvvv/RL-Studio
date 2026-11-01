import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ExtractedRequirementDraft } from '../../schemas/intent'
import { RequirementReviewList } from './RequirementReviewList'

function draft(id: string, description: string): ExtractedRequirementDraft {
  return {
    requirement_id: id,
    description,
    rule_type: 'expected_reward',
    parameters: { expected: 100 },
    tolerance: null,
    source: 'developer_confirmed',
    confirmed: null,
    environment_version: 'warehouse_v1',
  }
}

describe('RequirementReviewList', () => {
  it('lists accepted drafts with per-card actions and no auto-confirmation', () => {
    const onDecide = vi.fn()
    render(
      <RequirementReviewList
        extractionStatus="accepted"
        warnings={[]}
        pendingId={null}
        onDecide={onDecide}
        items={[
          { draft: draft('req_1', 'Goal reward must equal 100.') },
          { draft: draft('req_2', 'Step penalty must equal 1.') },
        ]}
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent('review before confirming')
    expect(screen.getAllByRole('button', { name: 'Confirm' })).toHaveLength(2)
    expect(screen.queryByText('Confirmed for this session')).not.toBeInTheDocument()
  })

  it('reports ambiguous extraction with the provider warnings and no cards', () => {
    render(
      <RequirementReviewList
        extractionStatus="ambiguous"
        warnings={['No exact expected value could be parsed.']}
        pendingId={null}
        onDecide={() => undefined}
        items={[]}
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent('could not be parsed unambiguously')
    expect(screen.getByText('No exact expected value could be parsed.')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('reports unsupported extraction outside the domain', () => {
    render(
      <RequirementReviewList
        extractionStatus="unsupported"
        warnings={['The statement is outside the supported warehouse-navigation domain.']}
        pendingId={null}
        onDecide={() => undefined}
        items={[]}
      />,
    )
    expect(
      screen.getByText('Intent is outside the supported domain', { exact: false }),
    ).toBeInTheDocument()
  })

  it('renders stated decisions and removes actions for decided drafts', () => {
    const onDecide = vi.fn()
    render(
      <RequirementReviewList
        extractionStatus="accepted"
        warnings={[]}
        pendingId={null}
        onDecide={onDecide}
        items={[{ draft: draft('req_1', 'Goal reward must equal 100.'), decision: 'confirm' }]}
      />,
    )

    expect(screen.getByText('Confirmed for this session')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
    expect(
      screen.getByText('backend persistence is not yet wired', { exact: false }),
    ).toBeInTheDocument()
  })

  it('disables only the card whose decision request is pending', () => {
    const onDecide = vi.fn()
    render(
      <RequirementReviewList
        extractionStatus="accepted"
        warnings={[]}
        pendingId="req_1"
        onDecide={onDecide}
        items={[
          { draft: draft('req_1', 'Goal reward must equal 100.') },
          { draft: draft('req_2', 'Step penalty must equal 1.') },
        ]}
      />,
    )

    const [firstConfirm, secondConfirm] = screen.getAllByRole('button', { name: 'Confirm' })
    expect(firstConfirm).toBeDisabled()
    expect(secondConfirm).toBeEnabled()
  })

  it('passing a null-id draft never produces decision actions', () => {
    render(
      <RequirementReviewList
        extractionStatus="accepted"
        warnings={[]}
        pendingId={null}
        onDecide={() => undefined}
        items={[{ draft: draft(null as unknown as string, 'Unassigned draft.') }]}
      />,
    )
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
