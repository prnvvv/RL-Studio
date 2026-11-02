import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'
import { EnvironmentsPage } from './EnvironmentsPage'

function renderPage() {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={['/environments']}>
        <EnvironmentsPage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('EnvironmentsPage', () => {
  it('labels the warehouse visual as a preview and reports missing state', () => {
    renderPage()

    expect(screen.getByRole('heading', { name: 'Simulation Environment' })).toBeInTheDocument()
    expect(
      screen.getByText(/Illustration preview\. Not a running simulation\./),
    ).toBeInTheDocument()
    expect(screen.getByText('Live simulation state unavailable')).toBeInTheDocument()
  })

  it('never presents enabled create or reset actions without a backend', () => {
    renderPage()

    expect(screen.getByRole('button', { name: 'Reset Environment' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'New Environment' })).toBeDisabled()
  })

  it('renders unavailable details instead of a plausible fabricated environment', () => {
    renderPage()

    expect(screen.getAllByText('Not available').length).toBeGreaterThan(0)
    expect(screen.getByText('Configuration form unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
})

describe('EnvironmentsPage with the mock opt-in (VITE_USE_MOCKS=true)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  function renderPageWithMocks() {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    renderPage()
  }

  it('plays the labeled sample replay instead of the still illustration', async () => {
    renderPageWithMocks()

    expect(screen.getByText(/Sample-data playback\. Not a live simulation\./)).toBeInTheDocument()
    await screen.findByTestId('warehouse-grid')
    expect(screen.getByText('Sample data')).toBeInTheDocument()
    expect(screen.queryByText('Illustration preview')).not.toBeInTheDocument()
  })

  it('keeps real playback controls and the recorded demo window visible', async () => {
    renderPageWithMocks()

    const slider = await screen.findByRole('slider')
    expect(slider).toHaveAttribute('aria-valuetext', 'Timestep 796 of 825')
    expect(
      screen.getByText(/Recorded timesteps 796–825 \u00b7 30 recorded positions/),
    ).toBeInTheDocument()
    expect(screen.getByTestId('fault-marker')).toBeInTheDocument()
  })

  it('keeps the honest no-record configuration panel in mock mode too', () => {
    renderPageWithMocks()

    expect(screen.getByText('Configuration form unavailable')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reset Environment' })).toBeDisabled()
  })
})
