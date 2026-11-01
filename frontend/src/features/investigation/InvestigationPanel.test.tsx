import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MOCK_DATA_LABEL, labeledMockData } from '../../mocks'
import type { InvestigationResult } from '../../schemas/investigation'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'
import { DEMO_INCIDENT_ID } from '../../mocks/verification'
import { investigateState } from './investigationState'
import { InvestigationPanel } from './InvestigationPanel'

const DEMO_RESULT: InvestigationResult = {
  investigation_id: 'inv_1',
  incident_id: DEMO_INCIDENT_ID,
  summary: 'Evidence implicates a changed goal-reward scale.',
  facts: [
    { statement: 'Goal reward was observed as 40 where the requirement expects 100.', evidence_refs: ['evt_812'] },
    { statement: 'Step-penalty checks passed unchanged.', evidence_refs: [] },
  ],
  contradictions: ['No contradictions recorded.'],
  hypotheses: [
    {
      hypothesis_id: 'hyp_1',
      statement: 'The environment goal-reward scale changed during the fault-injection interval.',
      reasoning: 'Only goal-reward observations diverge.',
      supporting_evidence_refs: ['evt_812'],
      confidence: 0.72,
    },
  ],
  alternatives: [
    { hypothesis_id: 'hyp_2', statement: 'The policy simply undertrained on the new layout.', reasoning: null, supporting_evidence_refs: [], confidence: null },
  ],
  recommended_tests: ['Re-run evaluation episodes in the healthy configuration.'],
  suggested_action: {
    action_type: 'restore_checkpoint',
    description: 'Assess the compatible pre-impact checkpoint.',
    target: 'ckpt_demo_pre_fault_1',
    requires_confirmation: true,
  },
  missing_evidence: ['No observation-checksum events are referenced.'],
  limitations: ['Sample data: produced by deterministic fixtures.'],
  provider: { provider: 'meta_model_api', model: null, prompt_version: null, schema_version: '1.0' },
  created_at: null,
  schema_version: '1.0',
}

type Mocked = ReturnType<typeof labeledMockData<InvestigationResult>>
type PanelState = ServiceQueryState<InvestigationResult | Mocked>

function renderPanel(overrides: {
  incidentId?: string | null
  investigation?: Partial<PanelState>
  onRequest?: () => void
  requestPending?: boolean
  onOpenEvidence?: (id: string) => void
} = {}) {
  const state: PanelState =
    overrides.investigation !== undefined
      ? ({ state: 'ok', data: DEMO_RESULT, ...overrides.investigation } as PanelState)
      : ({ state: 'ok', data: DEMO_RESULT } as unknown as PanelState)
  return render(
    <InvestigationPanel
      incidentId={overrides.incidentId !== undefined ? overrides.incidentId : DEMO_INCIDENT_ID}
      investigation={state}
      onRequest={overrides.onRequest}
      requestPending={overrides.requestPending}
      onOpenEvidence={overrides.onOpenEvidence}
    />,
  )
}

describe('InvestigationPanel', () => {
  it('renders a completed investigation with facts separated from hypotheses', () => {
    renderPanel()

    expect(screen.getByText('Investigation completed')).toBeInTheDocument()
    expect(screen.getByText('Observed facts')).toBeInTheDocument()
    expect(screen.getByText('Proposed hypotheses')).toBeInTheDocument()
    expect(screen.getByText('Goal reward was observed as 40 where the requirement expects 100.')).toBeInTheDocument()
    expect(screen.getByText(/The environment goal-reward scale changed/)).toBeInTheDocument()
  })

  it('labels fixture-backed analyses with the sample-data badge', () => {
    renderPanel({ investigation: { data: labeledMockData(DEMO_RESULT) } })
    expect(screen.getByText(MOCK_DATA_LABEL)).toBeInTheDocument()
  })

  it('presents the suggested action as a proposal requiring confirmation', () => {
    renderPanel()
    expect(screen.getByText('Suggested action — not executed')).toBeInTheDocument()
    expect(screen.getByText('Requires confirmation')).toBeInTheDocument()
    expect(screen.getByText(/Assess the compatible pre-impact checkpoint/)).toBeInTheDocument()
    expect(screen.getByText('Target: ckpt_demo_pre_fault_1')).toBeInTheDocument()
  })

  it('exposes missing evidence and provider metadata without inventing a model', () => {
    renderPanel()
    expect(screen.getByText('Missing evidence')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Missing evidence/ }))
    expect(screen.getByText('No observation-checksum events are referenced.')).toBeInTheDocument()

    expect(screen.getByText('Analysis details')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Analysis details/ }))
    expect(screen.getByText('meta_model_api')).toBeInTheDocument()
    expect(screen.getByText('not recorded')).toBeInTheDocument()
  })

  it('renders the not-run state as explicitly not run, with a request action', async () => {
    const onRequest = vi.fn(async () => undefined)
    renderPanel({
      investigation: {
        state: 'error',
        error: { kind: 'not_found', message: 'The requested record was not found.' },
        data: null,
      },
      onRequest,
    })

    expect(screen.getByText('No investigation recorded')).toBeInTheDocument()
    expect(screen.getByText('No investigation has been run')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Request investigation' }))
    expect(onRequest).toHaveBeenCalledOnce()
  })

  it('disables duplicate requests while one is pending', () => {
    renderPanel({
      investigation: {
        state: 'error',
        error: { kind: 'not_found', message: 'The requested record was not found.' },
        data: null,
      },
      onRequest: () => undefined,
      requestPending: true,
    })

    expect(screen.getByRole('button', { name: 'Requesting investigation…' })).toBeDisabled()
  })

  it('distinguishes provider unavailability from not-run-yet', () => {
    renderPanel({
      investigation: {
        state: 'error',
        error: { kind: 'unavailable', message: 'The service is currently unavailable.' },
        data: null,
      },
    })

    expect(screen.getByText('Provider unavailable')).toBeInTheDocument()
    expect(screen.queryByText('No investigation has been run')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Request investigation' })).not.toBeInTheDocument()
  })

  it('reports other failures without implying an analysis ran', () => {
    renderPanel({
      investigation: {
        state: 'error',
        error: { kind: 'server_error', message: 'The service encountered an internal error.' },
        data: null,
      },
    })
    expect(screen.getByText('The investigation could not be loaded')).toBeInTheDocument()
    expect(screen.getByText('Investigation failed')).toBeInTheDocument()
  })

  it('keeps retained findings visible and stale after a refresh failure', () => {
    renderPanel({
      investigation: {
        state: 'error',
        error: { kind: 'timeout', message: 'The request timed out; the backend operation state is unknown.' },
        data: DEMO_RESULT,
      },
    })

    expect(screen.getByText('Investigation could not be refreshed')).toBeInTheDocument()
    expect(screen.getByText('Investigation findings may be out of date')).toBeInTheDocument()
    expect(screen.getByText('Evidence implicates a changed goal-reward scale.')).toBeInTheDocument()
  })

  it('shows honest empty states when the provider returns no facts or hypotheses', () => {
    renderPanel({
      investigation: {
        data: {
          ...DEMO_RESULT,
          facts: [],
          hypotheses: [],
        },
      },
    })

    expect(screen.getByText('No observed facts were recorded for this investigation.')).toBeInTheDocument()
    expect(
      screen.getByText('The provider returned no hypotheses; no cause claim is implied.'),
    ).toBeInTheDocument()
  })

  it('navigates supporting evidence only through the explicit handler', () => {
    const onOpenEvidence = vi.fn()
    renderPanel({ onOpenEvidence })

    // evt_812 backs both a fact row and the hypothesis card; every instance
    // routes through the same handler.
    fireEvent.click(screen.getAllByRole('button', { name: 'evt_812' })[1] as HTMLElement)
    expect(onOpenEvidence).toHaveBeenCalledOnce()
    expect(onOpenEvidence).toHaveBeenCalledWith('evt_812')
  })

  it('renders skeletons while the investigation request is in flight', () => {
    renderPanel({ investigation: { state: 'loading' } as unknown as Partial<PanelState> })
    expect(screen.queryByText('Investigation completed')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Request investigation' })).not.toBeInTheDocument()
  })

  it('never requests an investigation implicitly when no incident is focused', () => {
    renderPanel({
      incidentId: null,
      investigation: {
        state: 'error',
        error: { kind: 'not_found', message: 'The requested record was not found.' },
        data: null,
      },
      onRequest: () => undefined,
    })

    expect(screen.queryByRole('button', { name: 'Request investigation' })).not.toBeInTheDocument()
    expect(screen.getByText('Focus an incident to make investigation available.')).toBeInTheDocument()
  })

  it('derives the badge state from service results only', () => {
    expect(investigateState({ state: 'loading' })).toBe('no_record')
    expect(
      investigateState({ state: 'error', error: { kind: 'not_found', message: 'x' }, data: null }),
    ).toBe('no_record')
    expect(
      investigateState({ state: 'error', error: { kind: 'unavailable', message: 'x' }, data: null }),
    ).toBe('provider_unavailable')
    expect(
      investigateState({ state: 'error', error: { kind: 'network', message: 'x' }, data: null }),
    ).toBe('failed')
  })
})
