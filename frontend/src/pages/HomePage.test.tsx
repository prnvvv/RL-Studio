import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { ThemeProvider } from '../contexts/ThemeContext'
import { HomePage } from './HomePage'

function renderHome() {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={['/']}>
        <HomePage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('HomePage', () => {
  it('renders the headline as the single h1', () => {
    renderHome()
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading).toHaveTextContent('Train. Monitor. Recover.')
  })

  it('offers the primary calls to action', () => {
    renderHome()

    expect(screen.getByRole('link', { name: 'Start Training' })).toHaveAttribute(
      'href',
      '/training',
    )
    expect(screen.getByRole('link', { name: 'View Environments' })).toHaveAttribute(
      'href',
      '/environments',
    )
    const loginLinks = screen.getAllByRole('link', { name: 'Login' })
    expect(loginLinks.length).toBeGreaterThanOrEqual(1)
    loginLinks.forEach((link) => expect(link).toHaveAttribute('href', '/login'))
    expect(screen.getByRole('link', { name: 'Describe intended behaviour' })).toHaveAttribute(
      'href',
      '/training#intent',
    )
  })

  it('shows the three capability pillars with their destinations', () => {
    renderHome()

    expect(screen.getByText('Fault detection')).toBeInTheDocument()
    expect(screen.getByText('Experience provenance')).toBeInTheDocument()
    expect(screen.getByText('Adaptive recovery')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open monitoring' })).toHaveAttribute(
      'href',
      '/monitoring',
    )
    expect(screen.getByRole('link', { name: 'Open diagnosis' })).toHaveAttribute(
      'href',
      '/diagnosis-recovery',
    )
    expect(screen.getByRole('link', { name: 'Open reports' })).toHaveAttribute('href', '/reports')
  })

  it('labels the warehouse figure as an illustration, not a running simulation', () => {
    renderHome()
    expect(screen.getByText('Illustration preview — not a running simulation.')).toBeInTheDocument()
  })
})
