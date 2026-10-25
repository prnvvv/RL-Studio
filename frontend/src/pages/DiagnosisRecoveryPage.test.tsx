import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'
import { DiagnosisRecoveryPage } from './DiagnosisRecoveryPage'

function renderPage() {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={['/diagnosis-recovery']}>
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
