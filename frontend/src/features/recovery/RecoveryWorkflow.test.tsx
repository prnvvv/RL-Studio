import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RecoveryStage, RecoveryWorkflow } from './RecoveryWorkflow'

const stages: RecoveryStage[] = [
  { id: 'select', label: 'Select checkpoint', state: 'completed', detail: 'ckpt_0007' },
  {
    id: 'validate',
    label: 'Validate compatibility',
    state: 'failed',
    detail: 'Algorithm mismatch',
  },
  { id: 'restore', label: 'Restore policy state', state: 'blocked' },
  { id: 'fresh', label: 'Collect fresh experience', state: 'pending' },
]

describe('RecoveryWorkflow', () => {
  it('renders the recorded plan in the supplied order with explicit states', () => {
    render(<RecoveryWorkflow stages={stages} planId="plan_01" />)

    const items = screen.getAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining('Select checkpoint'),
      expect.stringContaining('Validate compatibility'),
      expect.stringContaining('Restore policy state'),
      expect.stringContaining('Collect fresh experience'),
    ])

    expect(screen.getByText('Plan plan_01')).toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('Blocked')).toBeInTheDocument()
    expect(screen.getByText('Pending')).toBeInTheDocument()
  })

  it('renders nothing when no plan exists instead of assuming the canonical sequence', () => {
    const { container } = render(<RecoveryWorkflow stages={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
