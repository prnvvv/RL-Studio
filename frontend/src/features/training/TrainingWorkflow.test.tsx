import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TrainingWorkflow, WorkflowStage } from './TrainingWorkflow'

const stages: WorkflowStage[] = [
  { id: 'configure', label: 'Configure Environment', state: 'completed' },
  { id: 'train', label: 'Train Agent', state: 'current' },
  { id: 'faults', label: 'Inject Faults', state: 'pending' },
  { id: 'diagnose', label: 'Detect & Diagnose', state: 'blocked' },
  { id: 'recover', label: 'Recover', state: 'failed' },
  { id: 'evaluate', label: 'Evaluate', state: 'pending' },
]

describe('TrainingWorkflow', () => {
  it('renders all six stages with explicit state labels', () => {
    render(<TrainingWorkflow stages={stages} />)

    expect(screen.getByRole('list', { name: 'Training workflow stages' })).toBeInTheDocument()

    expect(screen.getByText('Configure Environment')).toBeInTheDocument()
    expect(screen.getByText('Train Agent')).toBeInTheDocument()
    expect(screen.getByText('Inject Faults')).toBeInTheDocument()
    expect(screen.getByText('Detect & Diagnose')).toBeInTheDocument()
    expect(screen.getByText('Recover')).toBeInTheDocument()
    expect(screen.getByText('Evaluate')).toBeInTheDocument()

    // State must never be communicated by colour alone.
    expect(screen.getByText('Completed')).toBeInTheDocument()
    expect(screen.getByText('Current')).toBeInTheDocument()
    expect(screen.getByText('Blocked')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getAllByText('Pending')).toHaveLength(2)
  })
})
