import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { ThemeProvider } from '../contexts/ThemeContext'
import { HomePage } from './HomePage'

function renderHome() {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={['/']}>
        <HomePage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('HomePage', () => {
  it('keeps the welcome actions and honest summary metrics', () => {
    renderHome()

    expect(screen.getByRole('heading', { name: 'Train. Monitor. Recover.' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Start Training' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View Environments' })).toBeInTheDocument()
    // No run data is loaded, so no metric claims a value.
    expect(screen.getAllByText('—')).toHaveLength(3)
  })

  it('links explicitly to the intent composer on the training page', () => {
    renderHome()

    const deepLink = screen.getByRole('link', { name: 'Describe intended behaviour' })
    expect(deepLink).toHaveAttribute('href', '/training#intent')
  })

  it('labels the warehouse figure as an illustration, not a running simulation', () => {
    renderHome()
    expect(screen.getByText('Illustration preview — not a running simulation.')).toBeInTheDocument()
  })
})
