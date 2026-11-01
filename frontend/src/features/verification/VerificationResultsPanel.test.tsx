import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MOCK_DATA_LABEL, labeledMockData } from '../../mocks'
import type { VerificationResult, EvidenceReference } from '../../schemas/verification'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'
import { VerificationResultsPanel } from './VerificationResultsPanel'

const verification: VerificationResult = {
  verification_id: 'ver_1',
  overall_status: 'fail',
  summary: 'One mandatory deterministic check failed.',
  results: [
    {
      requirement_id: 'req_goal_reward',
      status: 'fail',
      expected: 100,
      actual: 40,
      tolerance: null,
      evidence_refs: ['evt_1'],
      details: null,
      is_mandatory: true,
      timestamp: null,
    },
    {
      requirement_id: 'req_obs_integrity',
      status: 'unknown',
      expected: null,
      actual: null,
      tolerance: null,
      evidence_refs: [],
      details: null,
      is_mandatory: false,
      timestamp: null,
    },
  ],
  evidence_refs: ['evt_1'],
  warnings: [],
  errors: [],
  timestamp: null,
  schema_version: '1.0',
}

const evidence: EvidenceReference[] = [
  {
    id: 'evt_1',
    source: 'event_id',
    run_identifier: 'run_1',
    environment_identifier: 'warehouse_v1',
    location: null,
    timestamp: '2026-10-25T11:58:40Z',
  },
]

type MockedVerification = ReturnType<typeof labeledMockData<VerificationResult>>
type MockedEvidence = ReturnType<typeof labeledMockData<EvidenceReference[]>>
type VerificationState = ServiceQueryState<VerificationResult | MockedVerification>
type EvidenceState = ServiceQueryState<EvidenceReference[] | MockedEvidence>

function renderPanel(
  overrides: {
    verification?: Partial<VerificationState>
    evidence?: Partial<EvidenceState>
    onOpenEvidence?: (ref: string) => void
    onReload?: () => void
  } = {},
) {
  const verificationState: VerificationState =
    overrides.verification !== undefined
      ? ({ state: 'ok', data: verification, ...overrides.verification } as VerificationState)
      : ({ state: 'ok', data: verification } as unknown as VerificationState)
  const evidenceState: EvidenceState =
    overrides.evidence !== undefined
      ? ({ state: 'ok', data: evidence, ...overrides.evidence } as EvidenceState)
      : ({ state: 'ok', data: evidence } as unknown as EvidenceState)

  return render(
    <VerificationResultsPanel
      verification={verificationState}
      evidence={evidenceState}
      onOpenEvidence={overrides.onOpenEvidence}
      onReload={overrides.onReload}
    />,
  )
}

describe('VerificationResultsPanel', () => {
  it('renders loading skeletons while requests are in flight', () => {
    const { container } = renderPanel({
      verification: { state: 'loading' } as unknown as Partial<VerificationState>,
    })
    expect(screen.queryByText('Overall: failed')).not.toBeInTheDocument()
    expect(screen.queryByTestId('verdict-req_goal_reward')).not.toBeInTheDocument()
    expect(container.querySelectorAll('div').length).toBeGreaterThan(0)
  })

  it('renders loaded results with explicit expected vs observed values', () => {
    renderPanel()

    expect(screen.getByText('Overall: failed')).toBeInTheDocument()
    expect(screen.getByText('One mandatory deterministic check failed.')).toBeInTheDocument()
    expect(screen.getByTestId('verdict-req_goal_reward')).toBeInTheDocument()
    expect(screen.getByTestId('verdict-req_obs_integrity')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
    // Not-evaluable scope stays honest in the composed view too.
    expect(screen.getAllByText('Not evaluable').length).toBeGreaterThan(0)
  })

  it('attaches the sample-data badge to fixture-backed payloads', () => {
    renderPanel({
      verification: { data: labeledMockData(verification) },
      evidence: { data: labeledMockData(evidence) },
    })
    expect(screen.getByText(MOCK_DATA_LABEL)).toBeInTheDocument()
  })

  it('never attaches the sample-data badge to real payloads', () => {
    renderPanel()
    expect(screen.queryByText(MOCK_DATA_LABEL)).not.toBeInTheDocument()
  })

  it('renders evidence under the results and supports navigation', () => {
    const onOpenEvidence = vi.fn()
    renderPanel({ onOpenEvidence })

    // The id appears as a navigation target on the verdict card AND in the
    // evidence list; every instance routes through the same handler.
    const buttons = screen.getAllByRole('button', { name: 'evt_1' })
    expect(buttons.length).toBe(2)
    fireEvent.click(buttons[0] as HTMLElement)
    fireEvent.click(buttons[1] as HTMLElement)
    expect(onOpenEvidence).toHaveBeenCalledTimes(2)
    expect(onOpenEvidence).toHaveBeenCalledWith('evt_1')
  })

  it('shows an honest unavailable state with a retry path on failure', () => {
    const onReload = vi.fn()
    renderPanel({
      verification: {
        state: 'error',
        error: { kind: 'not_found', message: 'The requested record was not found.' },
        data: null,
      },
      onReload,
    })

    expect(screen.getByText('Verification results are unavailable')).toBeInTheDocument()
    expect(screen.queryByText('Overall: failed')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onReload).toHaveBeenCalledOnce()
  })

  it('keeps previously loaded results visible and marked stale after a later failure', () => {
    renderPanel({
      verification: {
        state: 'error',
        error: { kind: 'unavailable', message: 'The service is currently unavailable.' },
        data: verification,
      },
    })

    expect(screen.getByText('Verification could not be refreshed')).toBeInTheDocument()
    expect(screen.getByText('Verification results may be out of date')).toBeInTheDocument()
    // The retained results remain inspectable, never silently emptied.
    expect(screen.getByText('Overall: failed')).toBeInTheDocument()
  })

  it('reports an empty evidence scope and unavailable evidence listing distinctly', () => {
    renderPanel({ evidence: { data: [] } })
    expect(
      screen.getByText('No evidence references have been recorded for this verification scope.'),
    ).toBeInTheDocument()
  })

  it('shows the evidence listing failure inline while results stay visible', () => {
    renderPanel({
      evidence: {
        state: 'error',
        error: { kind: 'unavailable', message: 'The service is currently unavailable.' },
        data: null,
      },
    })
    expect(screen.getByText(/Evidence listing is not available right now/)).toBeInTheDocument()
    expect(screen.getByText('Overall: failed')).toBeInTheDocument()
  })

  it('renders a passing verdict set without failure styling', () => {
    renderPanel({
      verification: {
        data: {
          ...verification,
          overall_status: 'pass',
          summary: 'All applicable deterministic checks passed.',
          results: [
            {
              requirement_id: 'req_goal_reward',
              status: 'pass',
              expected: 100,
              actual: 100,
              tolerance: null,
              evidence_refs: [],
              details: null,
              is_mandatory: true,
              timestamp: null,
            },
          ],
        },
      },
    })

    expect(screen.getByText('Overall: passed')).toBeInTheDocument()
    expect(screen.queryByText('Overall: failed')).not.toBeInTheDocument()
    expect(screen.queryByText('Failed')).not.toBeInTheDocument()
  })
})
