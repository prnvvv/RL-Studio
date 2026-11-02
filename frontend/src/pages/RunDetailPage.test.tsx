import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'
import { RunDetailPage } from './RunDetailPage'
import { AppRouter } from '../app/router'

function renderPage(initialEntry = '/reports/run_1') {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AppRouter />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('RunDetailPage', () => {
  it('renders the run identifier from the path and a link back to Reports', () => {
    renderPage()

    expect(screen.getByRole('heading', { level: 1, name: 'Run run_1' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to Reports' })).toHaveAttribute(
      'href',
      '/reports',
    )
  })

  it('states no incident is connected when the URL carries no incidentId', () => {
    renderPage()

    expect(screen.getByText('No incident connected')).toBeInTheDocument()
    expect(
      screen.getByText(/Add \?incidentId=<incident> to the URL to connect one/),
    ).toBeInTheDocument()
  })

  it('marks incident-scoped sections not applicable without a connected incident', () => {
    renderPage()

    for (const title of ['Verification & Evidence', 'AI Investigation']) {
      const section = screen.getByRole('region', { name: title })
      expect(section).toHaveTextContent('Not applicable to this run')
    }

    const recovery = screen.getByRole('region', { name: 'Recovery' })
    expect(recovery).toHaveTextContent('Not applicable to this run')
    expect(recovery).toHaveTextContent(/recoveryId=<record>/)

    const evaluation = screen.getByRole('region', { name: 'Evaluation' })
    expect(evaluation).toHaveTextContent('Not applicable to this run')
    expect(evaluation).toHaveTextContent(/evaluationId=<record>/)
  })

  it('reports the requirements capability gap honestly instead of showing an unscoped list', () => {
    renderPage()

    const section = screen.getByRole('region', { name: 'Intent & Requirements' })
    expect(section).toHaveTextContent('Section unavailable')
    expect(section).toHaveTextContent(/not yet scoped by run/)
    expect(section).toHaveTextContent(/Required from: Person 3/)
  })

  it('renders run-scoped sections immediately since the run id always comes from the path', () => {
    renderPage()

    expect(
      screen.getByRole('region', { name: 'Visual debugging — Trajectory' }),
    ).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Provenance' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Training & Monitoring' })).toBeInTheDocument()
  })

  it('keeps every section isolated: independent fetch failures render side by side without blanking the page', async () => {
    renderPage()

    // No backend is reachable in this test environment. Each run-scoped
    // section performs its own independent request, so the honest network
    // failure appears more than once — one section's failure never removes
    // another section from the page.
    const failures = await screen.findAllByText(/The service could not be reached/i)
    expect(failures.length).toBeGreaterThan(1)

    // Sections that were already resolved as not-applicable stay visible too.
    expect(screen.getByRole('region', { name: 'Verification & Evidence' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Intent & Requirements' })).toBeInTheDocument()
  })

  it('connects incident-scoped sections from query params and attempts their own fetch', async () => {
    renderPage('/reports/run_1?incidentId=inc_1&evaluationId=eval_1&recoveryId=rec_1')

    expect(screen.getByText('Incident connected')).toBeInTheDocument()
    expect(screen.getByText(/Focused incident: inc_1/)).toBeInTheDocument()

    const verification = screen.getByRole('region', { name: 'Verification & Evidence' })
    expect(verification).not.toHaveTextContent('Not applicable to this run')

    const evaluation = screen.getByRole('region', { name: 'Evaluation' })
    expect(
      await within(evaluation).findByText(/The evaluation record could not be loaded/),
    ).toBeInTheDocument()

    const recovery = screen.getByRole('region', { name: 'Recovery' })
    expect(
      await within(recovery).findByText(/The service could not be reached/),
    ).toBeInTheDocument()
  })

  it('reports no run identifier rather than crashing when the path segment is missing', () => {
    render(
      <ThemeProvider>
        <MemoryRouter initialEntries={['/reports/']}>
          <RunDetailPage />
        </MemoryRouter>
      </ThemeProvider>,
    )

    // react-router does not match a trailing empty segment to `:runId`, so the
    // component's own defensive branch is exercised directly here.
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument()
  })
})
