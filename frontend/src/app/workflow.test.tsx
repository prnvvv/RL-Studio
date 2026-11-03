import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'
import { AppRouter } from './router'

/**
 * Cross-page navigation workflow (Phase 7 — `frontend/AGENTS.md` §21.7 item 1).
 *
 * Unlike `router.test.tsx` (which mounts each route independently), this
 * renders the application shell once and clicks through destinations in a
 * single session, the way a real user would: the shell must not remount,
 * the active-destination indicator must track the current route, and a
 * theme choice must survive navigating away and back.
 *
 * Primary-nav links are clicked through the "Primary" navigation landmark
 * rather than `screen.getByRole('link', ...)` directly: several pages (e.g.
 * Monitoring's related-views links) repeat a destination's name elsewhere
 * on the page, so an unscoped query would be ambiguous.
 */
function renderApp() {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={['/']}>
        <AppRouter />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

function primaryNav() {
  return screen.getByRole('navigation', { name: 'Primary' })
}

function clickPrimaryNav(label: string) {
  fireEvent.click(within(primaryNav()).getByRole('link', { name: label }))
}

const HOME_HEADING = 'Train. Monitor. Recover.'

describe('cross-page navigation workflow', () => {
  beforeEach(() => {
    // The landing route renders a particle scene; jsdom has no WebGL or
    // matchMedia, and the scene must degrade silently.
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
  })

  it('reaches every primary and secondary destination from one session without losing the shell', () => {
    renderApp()
    expect(screen.getByRole('heading', { level: 1, name: HOME_HEADING })).toBeInTheDocument()

    clickPrimaryNav('Training')
    expect(
      screen.getByRole('heading', { level: 1, name: 'Training Dashboard' }),
    ).toBeInTheDocument()
    expect(within(primaryNav()).getByRole('link', { name: 'Training' })).toHaveAttribute(
      'aria-current',
      'page',
    )

    clickPrimaryNav('Environments')
    expect(
      screen.getByRole('heading', { level: 1, name: 'Simulation Environment' }),
    ).toBeInTheDocument()

    clickPrimaryNav('Monitoring')
    expect(screen.getByRole('heading', { level: 1, name: 'Monitoring' })).toBeInTheDocument()

    clickPrimaryNav('Reports')
    expect(screen.getByRole('heading', { level: 1, name: 'Reports' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: 'Diagnosis & Recovery' }))
    expect(
      screen.getByRole('heading', { level: 1, name: 'Diagnosis & Recovery' }),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: 'Settings' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Settings' })).toBeInTheDocument()

    // The shell itself (product name, persistent header) never unmounted
    // across any of the above — it is still the same instance.
    expect(screen.getByText('Self-Healing RL Studio')).toBeInTheDocument()

    clickPrimaryNav('Home')
    expect(screen.getByRole('heading', { level: 1, name: HOME_HEADING })).toBeInTheDocument()
  })

  it('Open Studio on the home page enters the interactive studio workspace', async () => {
    // The studio asks the backend for its catalog; with it unreachable the
    // workspace must say so instead of listing agents it cannot run.
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('unreachable')))
    renderApp()
    fireEvent.click(screen.getByRole('link', { name: 'Open Studio' }))
    expect(
      await screen.findByRole('heading', { name: /studio backend is unavailable/i }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Primary' })).not.toBeInTheDocument()
  })

  it('keeps a theme choice across navigating away and back', () => {
    renderApp()
    clickPrimaryNav('Training')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')

    fireEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    clickPrimaryNav('Monitoring')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')

    clickPrimaryNav('Home')
    expect(screen.getByRole('heading', { level: 1, name: HOME_HEADING })).toBeInTheDocument()
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('updates the active-destination indicator as navigation proceeds, never on more than one link at a time', () => {
    renderApp()
    clickPrimaryNav('Training')

    clickPrimaryNav('Reports')
    const current = within(primaryNav())
      .getAllByRole('link')
      .filter((link) => link.getAttribute('aria-current'))
    expect(current).toHaveLength(1)
    expect(current[0]).toHaveAttribute('href', '/reports')
  })
})
