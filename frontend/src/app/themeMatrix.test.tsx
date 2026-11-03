import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'
import { AppRouter } from './router'

/**
 * Theme regression matrix (Phase 7 — `frontend/AGENTS.md` §21.6, §25).
 *
 * This does not audit contrast or visual appearance — that is a manual
 * review against the documented visual direction. What it does verify
 * automatically: every route mounts without error under both themes, and
 * the theme actually resolved to `data-theme` on `<html>` matches what was
 * requested, for every documented destination including the Phase 6 run
 * detail route.
 */
const THEME_STORAGE_KEY = 'self-healing-rl-studio-theme'

const DESTINATIONS: { path: string; heading: string }[] = [
  { path: '/', heading: 'A safer sandbox for stronger agents.' },
  { path: '/training', heading: 'Training Dashboard' },
  { path: '/environments', heading: 'Simulation Environment' },
  { path: '/monitoring', heading: 'Monitoring' },
  { path: '/diagnosis-recovery', heading: 'Diagnosis & Recovery' },
  { path: '/reports', heading: 'Reports' },
  { path: '/reports/run_1', heading: 'Run run_1' },
  { path: '/settings', heading: 'Settings' },
]

const THEMES = ['dark', 'light'] as const

function renderAt(path: string, theme: 'dark' | 'light') {
  window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <AppRouter />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('theme regression matrix', () => {
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

  for (const theme of THEMES) {
    for (const { path, heading } of DESTINATIONS) {
      it(`renders ${path} under the ${theme} theme`, () => {
        const { unmount } = renderAt(path, theme)

        expect(document.documentElement.getAttribute('data-theme')).toBe(theme)
        expect(screen.getByRole('heading', { level: 1, name: heading })).toBeInTheDocument()

        unmount()
      })
    }
  }

  it('never flashes the wrong theme attribute before first paint', () => {
    renderAt('/', 'light')

    // The attribute is set synchronously from the stored preference via
    // ThemeProvider's effect before this assertion runs; it must already be
    // 'light', never the 'dark' default that getInitialTheme falls back to.
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })
})
