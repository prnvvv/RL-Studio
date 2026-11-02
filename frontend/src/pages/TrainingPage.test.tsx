import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../contexts/ThemeContext'
import { TrainingPage } from './TrainingPage'

function renderTraining(initialEntry = '/training') {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <TrainingPage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

/** Prints the current query string so scope changes are observable. */
function LocationEcho() {
  const location = useLocation()
  return <span data-testid="location">{`${location.pathname}${location.search}`}</span>
}

describe('TrainingPage', () => {
  it('keeps all existing sections and adds the intent composer panel', () => {
    renderTraining()

    // Existing functionality untouched.
    expect(screen.getByRole('heading', { name: 'Training Dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Workflow' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Reward vs. Training Steps' })).toBeInTheDocument()

    // New section with its anchor and composer.
    expect(screen.getByRole('heading', { name: 'Intent & Requirements' })).toBeInTheDocument()
    expect(document.getElementById('intent')).not.toBeNull()
    expect(screen.getByLabelText('Intended behaviour')).toBeInTheDocument()
    // The dictation control is feature-detected; jsdom has no engine.
    expect(screen.getByText('Dictation unavailable in this browser')).toBeInTheDocument()
  })

  it('renders with the #intent deep link without disturbing navigation context', () => {
    const probe = vi.fn()
    function HashProbe() {
      const location = useLocation()
      probe(location.hash)
      return null
    }
    render(
      <ThemeProvider>
        <MemoryRouter initialEntries={['/training#intent']}>
          <HashProbe />
          <TrainingPage />
        </MemoryRouter>
      </ThemeProvider>,
    )
    expect(probe).toHaveBeenCalledWith('#intent')
    expect(document.getElementById('intent')).not.toBeNull()
  })

  it('surfaces a failed intent submission as an honest error, not empty data', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ detail: 'Not Found' }), { status: 404 })),
    )
    renderTraining()

    fireEvent.change(screen.getByLabelText('Intended behaviour'), {
      target: { value: 'The goal reward must be 100.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Submit intent' }))

    await waitFor(() =>
      expect(screen.getByText('The intent could not be submitted')).toBeInTheDocument(),
    )
    // The failed request must never be turned into an empty review list.
    expect(screen.queryByText('Requirements extracted')).not.toBeInTheDocument()
    vi.unstubAllGlobals()
  })

  it('keeps the page unscoped and honest until a run identifier is supplied', () => {
    renderTraining()

    expect(screen.getByRole('heading', { name: 'Run lifecycle' })).toBeInTheDocument()
    expect(screen.getByText('No run selected')).toBeInTheDocument()
    // No lifecycle read is attempted without a run, so no status notice appears.
    expect(screen.queryByText('Run status unavailable')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start training' })).not.toBeInTheDocument()
  })

  it('moves focus to the run scope form instead of pretending a creation flow exists', () => {
    renderTraining()

    fireEvent.click(screen.getByRole('button', { name: 'New Training Run' }))

    expect(document.activeElement).toBe(screen.getByLabelText('Run identifier'))
  })

  it('commits the run scope to the URL so a refresh or shared link keeps it', async () => {
    render(
      <ThemeProvider>
        <MemoryRouter initialEntries={['/training']}>
          <LocationEcho />
          <TrainingPage />
        </MemoryRouter>
      </ThemeProvider>,
    )

    fireEvent.change(screen.getByLabelText('Run identifier'), { target: { value: 'run_9' } })
    fireEvent.click(screen.getByRole('button', { name: 'Use run' }))

    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/training?runId=run_9'),
    )
  })

  it('reports an unreadable run status and keeps start/stop fail-closed', async () => {
    // No backend is reachable from the test environment, so the status read
    // fails rather than returning a fabricated lifecycle.
    renderTraining('/training?runId=run_1')

    await waitFor(() => expect(screen.getByText('Run status unavailable')).toBeInTheDocument())

    const start = screen.getByRole('button', { name: 'Start training' })
    const stop = screen.getByRole('button', { name: 'Stop run' })
    expect(start).toBeDisabled()
    expect(stop).toBeDisabled()
    expect(
      screen.getByText(/The current run state has not been read, so starting is blocked/i),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/The current run state has not been read, so stopping is blocked/i),
    ).toBeInTheDocument()

    // Re-reading a status endpoint is side-effect free, so a retry is offered.
    expect(screen.getByRole('button', { name: 'Refresh status' })).toBeInTheDocument()
  })

  it('links the selected run to monitoring without inventing metrics', async () => {
    renderTraining('/training?runId=run_1')

    await waitFor(() => expect(screen.getByText('Run status unavailable')).toBeInTheDocument())

    expect(screen.getByRole('link', { name: 'Open live monitoring for this run' })).toHaveAttribute(
      'href',
      '/monitoring?runId=run_1',
    )
    // The chart stays explicitly empty: no metrics endpoint is bound.
    expect(screen.getByText('No training metrics available')).toBeInTheDocument()
  })
})
