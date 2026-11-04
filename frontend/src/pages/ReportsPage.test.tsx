import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'
import { ReportsPage } from './ReportsPage'

function renderPage(initialEntry = '/reports') {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <ReportsPage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('ReportsPage', () => {
  it('shows the title, subtitle, and a labelled filter control', () => {
    renderPage()

    expect(screen.getByRole('heading', { level: 1, name: 'Reports' })).toBeInTheDocument()
    expect(
      screen.getByText(/compare recorded training and evaluation outcomes/i),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Filter runs')).toBeInTheDocument()
  })

  it('renders the six documented columns even with no records', () => {
    renderPage()

    const table = screen.getByRole('table')
    const headers = within(table).getAllByRole('columnheader')
    expect(headers.map((header) => header.textContent)).toEqual([
      'Run ID',
      'Environment',
      'Steps',
      'Success Rate',
      'Status',
      'Date',
    ])
  })

  it('states that no run records exist instead of showing example rows', () => {
    renderPage()

    expect(screen.getByText('No run records')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(2) // header + empty cell
    expect(screen.queryByText('run_0001')).not.toBeInTheDocument()
  })

  it('does not present the page as live, historical, or demo data', () => {
    renderPage()

    expect(screen.getByText('No data source')).toBeInTheDocument()
    expect(
      screen.getByText(/Nothing on this page is live, historical, or demonstration data/i),
    ).toBeInTheDocument()
  })

  it('explains why the filter is disabled rather than letting it silently do nothing', () => {
    renderPage()

    const input = screen.getByLabelText('Filter runs')
    expect(input).toBeDisabled()
    expect(screen.getByRole('status', { name: 'Filter results' })).toHaveTextContent(
      /nothing to filter/i,
    )
  })

  it('never renders an export action while export is unimplemented', () => {
    renderPage()

    expect(screen.queryByRole('button', { name: /export|download/i })).not.toBeInTheDocument()
    expect(
      screen.getByText(/Export is unavailable until a real export capability exists/i),
    ).toBeInTheDocument()
  })

  it('offers no per-row actions', () => {
    renderPage()

    const table = screen.getByRole('table')
    expect(within(table).queryAllByRole('button')).toHaveLength(0)
    expect(within(table).queryAllByRole('link')).toHaveLength(0)
  })

  it('shows evaluation comparison as unavailable rather than drawing an empty chart', () => {
    renderPage()

    const summary = screen.getByRole('region', { name: 'Evaluation Summary' })
    expect(summary).toHaveTextContent('No evaluation records')
    expect(within(summary).queryByRole('img')).not.toBeInTheDocument()
  })

  it('displays a connected evaluation record honestly when ids are supplied', async () => {
    renderPage('/reports?incidentId=inc_demo&evaluationId=eval_demo')

    // No live evaluation endpoint exists in the test environment, so the
    // honest mapped failure is shown instead of a fabricated comparison.
    const summary = await screen.findByRole('region', { name: 'Evaluation Summary' })
    expect(
      await within(summary).findByText(/The evaluation record could not be loaded/),
    ).toBeInTheDocument()
    // The empty-state claim no longer applies while a record is connected.
    expect(within(summary).queryByText('No evaluation records')).not.toBeInTheDocument()
  })
  it('presents the redesigned header and marks Reports as the active destination', () => {
    renderPage()
    expect(screen.getByText('Training analytics')).toBeInTheDocument()
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getByRole('link', { name: 'Reports' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(within(nav).getAllByRole('link', { current: 'page' })).toHaveLength(1)
  })

  it('uses a purposeful empty state with no decorative image role or fabricated rows', () => {
    renderPage()
    const history = screen.getByRole('region', { name: 'Run History' })
    expect(within(history).getByText('No run records')).toBeInTheDocument()
    expect(
      within(history).getByText('Training history appears here once the backend records runs.'),
    ).toBeInTheDocument()
    expect(within(history).queryByRole('img')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /run_/ })).not.toBeInTheDocument()
  })
})
