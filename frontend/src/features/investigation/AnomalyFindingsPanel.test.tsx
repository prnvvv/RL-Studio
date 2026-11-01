import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { AnomalyObservation } from '../../schemas/verification'
import { AnomalyFindingsPanel } from './AnomalyFindingsPanel'

function anomaly(overrides: Partial<AnomalyObservation> = {}): AnomalyObservation {
  return {
    anomaly_id: 'ano_demo',
    anomaly_type: 'reward_deviation',
    score: 0.82,
    threshold: 0.5,
    description: 'Goal-reward observations deviate from the recorded expectation.',
    evidence_refs: ['evt_demo_step_812'],
    timestamp: null,
    ...overrides,
  }
}

describe('AnomalyFindingsPanel', () => {
  it('shows an honest empty state when no anomalies are recorded', () => {
    render(<AnomalyFindingsPanel anomalies={[]} />)
    expect(screen.getByText('No anomaly observations recorded')).toBeInTheDocument()
    expect(screen.queryByText(/Detector score/)).not.toBeInTheDocument()
  })

  it('renders the detector signal with score and threshold', () => {
    render(<AnomalyFindingsPanel anomalies={[anomaly()]} />)
    expect(screen.getByText('Reward deviation')).toBeInTheDocument()
    expect(screen.getByText('Detector score 0.82 (trigger threshold 0.5)')).toBeInTheDocument()
    expect(screen.getByText('Goal-reward observations deviate from the recorded expectation.')).toBeInTheDocument()
  })

  it('always keeps the not-a-confirmed-fault disclaimer visible', () => {
    render(<AnomalyFindingsPanel anomalies={[anomaly({ evidence_refs: [] })]} />)
    expect(screen.getByText(/Detector signal — not a confirmed fault/)).toBeInTheDocument()
  })

  it('renders partial score information when only one value is recorded', () => {
    render(<AnomalyFindingsPanel anomalies={[anomaly({ score: null })]} />)
    expect(screen.getByText('Trigger threshold 0.5')).toBeInTheDocument()

    const { unmount } = render(<AnomalyFindingsPanel anomalies={[anomaly({ threshold: null })]} />)
    expect(screen.getByText('Detector score 0.82')).toBeInTheDocument()
    unmount()
    expect(screen.queryByText(/Detector score/)).not.toBeInTheDocument()
  })

  it('navigates to evidence only through the explicit handler', () => {
    const onOpenEvidence = vi.fn()
    render(<AnomalyFindingsPanel anomalies={[anomaly()]} onOpenEvidence={onOpenEvidence} />)

    fireEvent.click(screen.getByRole('button', { name: 'evt_demo_step_812' }))
    expect(onOpenEvidence).toHaveBeenCalledWith('evt_demo_step_812')
  })
})
