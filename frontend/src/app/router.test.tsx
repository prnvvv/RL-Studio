import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'
import { AppRouter } from './router'

function renderRoute(path: string) {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRouter />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('AppRouter', () => {
  it('renders a distinct heading for every documented destination', () => {
    const destinations = [
      { path: '/', heading: 'Train. Monitor. Recover.' },
      { path: '/training', heading: 'Training Dashboard' },
      { path: '/environments', heading: 'Simulation Environment' },
      { path: '/monitoring', heading: 'Monitoring' },
      { path: '/diagnosis-recovery', heading: 'Diagnosis & Recovery' },
      { path: '/reports', heading: 'Training History' },
      { path: '/settings', heading: 'Settings' },
    ]

    destinations.forEach(({ path, heading }) => {
      const { unmount } = render(
        <ThemeProvider>
          <MemoryRouter initialEntries={[path]}>
            <AppRouter />
          </MemoryRouter>
        </ThemeProvider>,
      )
      expect(screen.getByRole('heading', { level: 1, name: heading })).toBeInTheDocument()
      unmount()
    })
  })

  it('shows a not-found surface for an unknown URL without changing state', () => {
    renderRoute('/does-not-exist')

    expect(screen.getByRole('heading', { level: 1, name: 'This page does not exist' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to overview' })).toHaveAttribute('href', '/')
  })
})
