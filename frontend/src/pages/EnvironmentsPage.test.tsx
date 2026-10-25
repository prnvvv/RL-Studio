import { describe, expect, it } from 'vitest'
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
    expect(screen.getByText(/Illustration preview\. Not a running simulation\./)).toBeInTheDocument()
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
