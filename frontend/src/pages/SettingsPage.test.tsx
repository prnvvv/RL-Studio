import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'
import { SettingsPage } from './SettingsPage'

function renderPage(path = '/settings') {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <SettingsPage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('SettingsPage', () => {
  it('renders the title, subtitle, and a labelled secondary navigation', () => {
    renderPage()

    expect(screen.getByRole('heading', { level: 1, name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Settings sections' })).toBeInTheDocument()
  })

  it('lists only sections with supported behaviour and marks the active one', () => {
    renderPage()

    const nav = screen.getByRole('navigation', { name: 'Settings sections' })
    const links = within(nav).getAllByRole('link')
    expect(links.map((link) => link.textContent)).toEqual(['Appearance'])
    expect(links[0]).toHaveAttribute('aria-current', 'page')
    expect(links[0]).toHaveAttribute('href', '/settings#appearance')
  })

  it('does not render navigable Profile, Environment, Training, Notifications, or Integrations sections', () => {
    renderPage()

    const nav = screen.getByRole('navigation', { name: 'Settings sections' })
    for (const label of ['Profile', 'Environment', 'Training', 'Notifications', 'Integrations']) {
      expect(within(nav).queryByRole('link', { name: label })).not.toBeInTheDocument()
    }
  })

  it('explains why the unavailable sections are absent instead of hiding the gap', () => {
    renderPage()

    const panel = screen.getByRole('region', { name: 'Not available yet' })
    expect(within(panel).getByText('Profile')).toBeInTheDocument()
    expect(within(panel).getByText(/authentication/i)).toBeInTheDocument()
    expect(within(panel).getByText('Integrations')).toBeInTheDocument()
    // Informational only: no controls that pretend to configure anything.
    expect(within(panel).queryAllByRole('button')).toHaveLength(0)
    expect(within(panel).queryAllByRole('link')).toHaveLength(0)
    expect(within(panel).queryAllByRole('checkbox')).toHaveLength(0)
    expect(within(panel).queryAllByRole('switch')).toHaveLength(0)
  })

  it('shows the appearance setting with the current theme selected', () => {
    renderPage()

    expect(screen.getByRole('radio', { name: /^Dark/ })).toBeChecked()
    expect(screen.getByRole('heading', { level: 2, name: 'Appearance' })).toBeInTheDocument()
  })

  it('applies and persists a theme change made from the settings page', () => {
    renderPage()

    fireEvent.click(screen.getByRole('radio', { name: /^Light/ }))

    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(window.localStorage.getItem('self-healing-rl-studio-theme')).toBe('light')
  })

  it('keeps the header toggle and the settings control on one source of truth', () => {
    renderPage()

    // Header offers the opposite theme while the app is dark.
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('radio', { name: /^Light/ }))

    // The header reflects the change immediately: no second preference store.
    expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /^Light/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: /^Dark/ })).not.toBeChecked()

    // And the header control writes back to the same store.
    fireEvent.click(screen.getByRole('button', { name: 'Switch to dark theme' }))
    expect(screen.getByRole('radio', { name: /^Dark/ })).toBeChecked()
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
  })

  it('reports an unknown section hash without redirecting silently', () => {
    renderPage('/settings#profile')

    expect(screen.getByRole('region', { name: 'Unknown section' })).toHaveTextContent(
      'No settings section named “profile” exists',
    )
    expect(screen.getByRole('link', { name: 'Go to Appearance' })).toHaveAttribute(
      'href',
      '/settings#appearance',
    )
  })

  it('renders no fake save, edit, or profile controls anywhere', () => {
    renderPage()

    expect(
      screen.queryByRole('button', { name: /save|edit profile|sign in|connect/i }),
    ).not.toBeInTheDocument()
    expect(screen.queryAllByRole('switch')).toHaveLength(0)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
})
