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

// The real service runs in test env in real mode (mocks disabled), so page
// submissions hit the planned endpoints only if a backend exists; this test
// file keeps state assertions light and leaves detailed flows to the
// composer / service suites.
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

    fireEvent.change(screen.getByLabelText('Intended behaviour'), { target: { value: 'The goal reward must be 100.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit intent' }))

    await waitFor(() => expect(screen.getByText('The intent could not be submitted')).toBeInTheDocument())
    // The failed request must never be turned into an empty review list.
    expect(screen.queryByText('Requirements extracted')).not.toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})
