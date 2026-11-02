import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'
import { mockInvestigationAdapter } from '../mocks/investigation'
import { DiagnosisRecoveryPage } from './DiagnosisRecoveryPage'
import { DEMO_INCIDENT_ID } from '../mocks/verification'

function renderPage(initialEntry = '/diagnosis-recovery') {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <DiagnosisRecoveryPage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('DiagnosisRecoveryPage', () => {
  it('states that AI analysis is advisory rather than authoritative', () => {
    renderPage()

    expect(
      screen.getByRole('heading', { level: 1, name: 'Diagnosis & Recovery' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Advisory analysis')).toBeInTheDocument()
    expect(screen.getByText(/not a proof of cause/i)).toBeInTheDocument()
  })

  it('does not claim a root cause or validated conclusion when no incident is loaded', () => {
    renderPage()

    expect(screen.getByText('No root cause available')).toBeInTheDocument()
    expect(screen.getByText('No incident loaded')).toBeInTheDocument()
    expect(screen.queryByText(/likely cause/i)).not.toBeInTheDocument()

    // No badge is rendered with the "strong" (validated conclusion) tone.
    expect(document.querySelector('[data-tone="strong"]')).toBeNull()
  })

  it('provides the three required disclosure sections, collapsed by default', () => {
    renderPage()

    for (const title of ['Evidence Used', 'Analysis Details', 'Recommended Recovery Plan']) {
      expect(screen.getByRole('button', { name: new RegExp(title) })).toHaveAttribute(
        'aria-expanded',
        'false',
      )
    }
  })

  it('marks expected and observed values as unavailable instead of deriving them from metrics', () => {
    renderPage()

    const incident = screen.getByRole('region', { name: 'Incident' })
    expect(within(incident).getByText('Expected value')).toBeInTheDocument()
    expect(within(incident).getByText('Observed value')).toBeInTheDocument()
    expect(within(incident).getAllByText('Not available').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: /Evidence Used/ }))
    expect(screen.getByRole('region', { name: /Evidence Used/ })).toHaveTextContent(
      /incident package is loaded/i,
    )
  })

  it('offers no recovery action before preflight and approval records exist', () => {
    renderPage()

    expect(screen.getByText('No recovery plan')).toBeInTheDocument()

    // The recovery area contains no actionable control at all, so a user cannot
    // request an unvalidated restore.
    const recovery = screen.getByRole('region', { name: 'Recovery' })
    expect(within(recovery).queryAllByRole('button')).toHaveLength(0)
  })

  it('keeps proposed and executed recovery actions, and evaluation, as separate fields', () => {
    renderPage()

    const recovery = screen.getByRole('region', { name: 'Recovery' })
    expect(within(recovery).getByText('Proposed action')).toBeInTheDocument()
    expect(within(recovery).getByText('Executed action')).toBeInTheDocument()
    expect(within(recovery).getByText('Evaluation status')).toBeInTheDocument()
    expect(
      within(recovery).getByText(/reported as successful only when the evaluation record/i),
    ).toBeInTheDocument()
  })
})

describe('DiagnosisRecoveryPage with a focused incident (sample-data mode)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    mockInvestigationAdapter.resetMockInvestigationState()
  })

  function renderFocused() {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    renderPage(`/diagnosis-recovery?incidentId=${DEMO_INCIDENT_ID}`)
  }

  it('loads the incident record and the labeled deterministic verification', async () => {
    renderFocused()

    // Fixture-backed payloads carry the shared sample-data label.
    expect(await screen.findAllByText('Sample data')).not.toHaveLength(0)

    expect(await screen.findByText('Overall: failed')).toBeInTheDocument()
    // The requirement id appears both in the incident rows and its verdict card.
    expect((await screen.findAllByText('req_demo_goal_reward')).length).toBeGreaterThan(0)
    // The canonical fault is visible as an explicit mismatch: expected 100 vs observed 40.
    expect(await screen.findByText('100')).toBeInTheDocument()
    expect(await screen.findByText('40')).toBeInTheDocument()
    // Not-evaluable scope stays honest inside the composed page.
    expect(await screen.findAllByText('Not evaluable')).not.toHaveLength(0)

    const incident = screen.getByRole('region', { name: 'Incident' })
    expect(within(incident).getByText('inc_demo_warehouse_reward_scale')).toBeInTheDocument()
    expect(within(incident).getAllByText('Not available').length).toBeGreaterThan(0)
  })

  it('plays the run trajectory with markers only at recorded evidence events', async () => {
    renderFocused()

    // The incident record names the run; the panel loads that run's replay.
    const trajectory = await screen.findByRole('region', { name: 'Recorded trajectory' })
    const grid = await within(trajectory).findByTestId('warehouse-grid')
    expect(within(trajectory).getAllByText('Sample data')).not.toHaveLength(0)
    // The label binds samples and live claims apart inside the panel.
    expect(grid.getAttribute('aria-label') ?? '').toMatch(/recorded replay; not a live simulation/i)

    // Playback starts at the recording's first recorded timestep.
    await within(trajectory).findByRole('slider')
    expect(within(trajectory).getByRole('slider')).toHaveAttribute(
      'aria-valuetext',
      'Timestep 796 of 825',
    )

    // Only the incident's recorded evidence event is annotated — nothing is
    // inferred from metric context.
    const markers = within(trajectory).getAllByTestId('fault-marker')
    expect(markers).toHaveLength(1)
    expect(markers[0]).toHaveAttribute('data-event-id', 'evt_demo_step_812')
  })

  it('labels anomaly findings as detector signals, not confirmed faults', async () => {
    renderFocused()

    const anomalies = await screen.findByRole('region', { name: 'Anomaly findings' })
    expect(
      await within(anomalies).findByText(/Detector signal — not a confirmed fault/),
    ).toBeInTheDocument()
  })

  it('starts with no investigation recorded and records one after an explicit request', async () => {
    renderFocused()

    const diagnosis = await screen.findByRole('region', { name: 'AI Diagnosis' })
    expect(await within(diagnosis).findByText('No investigation has been run')).toBeInTheDocument()

    // Nothing requested an analysis implicitly — the panel opens with the
    // explicit request control only.
    fireEvent.click(await within(diagnosis).findByRole('button', { name: 'Request investigation' }))

    // The recorded (still sample-labeled) analysis then renders from the service.
    expect(await screen.findByText('Investigation completed')).toBeInTheDocument()
    expect(screen.getByText('Suggested action — not executed')).toBeInTheDocument()
    expect(screen.getByText('Requires confirmation')).toBeInTheDocument()
  })

  it('offers no recovery action while no recovery plan record exists', () => {
    renderFocused()

    const recovery = screen.getByRole('region', { name: 'Recovery' })
    expect(within(recovery).getByText('No recovery plan')).toBeInTheDocument()
    expect(within(recovery).queryAllByRole('button')).toHaveLength(0)
  })

  it('keeps the live recovery workflow as an explicit section without a recorded assessment', async () => {
    renderFocused()

    // The live workflow is its own region, distinct from the page-level
    // recovery record region; requesting an assessment is explicit.
    const workflow = await screen.findByRole('region', { name: 'Recovery workflow' })
    expect(
      await within(workflow).findByText(/computes eligibility and compatibility itself/i),
    ).toBeInTheDocument()
    expect(
      await within(workflow).findByText(/No assessment is supplied for this incident yet/),
    ).toBeInTheDocument()
    // The explicit assessment request is the only control, and the gated
    // execution request does not exist until the assessment record opens it.
    const buttons = within(workflow).getAllByRole('button')
    expect(buttons).toHaveLength(1)
    expect(buttons[0]!.textContent).toContain('Request compatibility assessment')
    expect(within(workflow).queryByText(/Request controlled recovery/)).not.toBeInTheDocument()
  })

  it('reports an assessment-request failure honestly without fabricating an assessment', async () => {
    renderFocused()

    const workflow = await screen.findByRole('region', { name: 'Recovery workflow' })
    const buttons = within(workflow).getAllByRole('button')
    expect(buttons).toHaveLength(1) // the explicit assessment request is the only control
    fireEvent.click(within(workflow).getAllByRole('button')[0]!)

    // The live provider does not exist in this test environment, so the page
    // reports the honest mapped failure instead of a fabricated record.
    expect(
      await within(workflow).findByText(/The assessment request could not be completed/),
    ).toBeInTheDocument()
    expect(within(workflow).queryByText('Eligibility: eligible')).not.toBeInTheDocument()
  })

  it('states that no evaluation record is connected when no id is supplied', async () => {
    renderFocused()

    const evaluation = await screen.findByRole('region', { name: 'Evaluation' })
    expect(
      await within(evaluation).findByText(/No evaluation record is connected to this view/),
    ).toBeInTheDocument()
    expect(within(evaluation).queryByText(/Recovery verified/)).not.toBeInTheDocument()
  })

  it('reports an evaluation fetch failure honestly when a record id is connected', async () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    renderPage(`/diagnosis-recovery?incidentId=${DEMO_INCIDENT_ID}&evaluationId=eval_demo`)

    // No live evaluation endpoint exists in the test environment; the honest
    // mapped failure is displayed rather than any computed outcome.
    expect(await screen.findByText(/The evaluation record could not be loaded/)).toBeInTheDocument()
  })

  it('keeps the no-incident focus claim when the URL has no incident id', () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    renderPage()

    expect(screen.getByText('No incident loaded')).toBeInTheDocument()
    expect(screen.queryByText('Deterministic verification')).not.toBeInTheDocument()
  })
})
