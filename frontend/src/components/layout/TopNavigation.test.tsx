import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../../contexts/ThemeContext'
import { TopNavigation } from './TopNavigation'

const ALL_DESTINATIONS = [
  'Projects',
  'Home',
  'Training',
  'Environments',
  'Monitoring',
  'Reports',
  'Diagnosis & Recovery',
  'Settings',
]

/** Controllable fake so each test can force wide or narrow without real CSS. */
function stubViewport(matchesNarrow: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: matchesNarrow,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }))
}

function renderNav(initialEntry = '/') {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <TopNavigation />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('TopNavigation at desktop width', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows every destination inline with no menu button', () => {
    stubViewport(false)
    renderNav()

    for (const label of ALL_DESTINATIONS) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
    }
    expect(screen.queryByRole('button', { name: /navigation menu/i })).not.toBeInTheDocument()
  })
})

describe('TopNavigation at narrow width', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('collapses the destinations behind a labelled, closed-by-default menu button', () => {
    stubViewport(true)
    renderNav()

    for (const label of ALL_DESTINATIONS) {
      expect(screen.queryByRole('link', { name: label })).not.toBeInTheDocument()
    }
    const toggle = screen.getByRole('button', { name: 'Open navigation menu' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('still keeps every destination reachable once the menu is opened', () => {
    stubViewport(true)
    renderNav()

    fireEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }))

    expect(screen.getByRole('button', { name: 'Close navigation menu' })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    for (const label of ALL_DESTINATIONS) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
    }
  })

  it('dismisses the menu on Escape without navigating away', () => {
    stubViewport(true)
    renderNav()

    fireEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }))
    expect(screen.getByRole('link', { name: 'Training' })).toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.queryByRole('link', { name: 'Training' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open navigation menu' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
  })

  it('dismisses the menu after choosing a destination from it', () => {
    stubViewport(true)
    renderNav()

    fireEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }))
    fireEvent.click(screen.getByRole('link', { name: 'Training' }))

    expect(screen.queryByRole('link', { name: 'Training' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open navigation menu' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
  })

  it('still highlights the active destination inside the collapsed menu', () => {
    stubViewport(true)
    renderNav('/monitoring')

    fireEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }))

    expect(screen.getByRole('link', { name: 'Monitoring' })).toHaveAttribute('aria-current', 'page')
  })

  it('keeps the theme toggle reachable without opening the menu', () => {
    stubViewport(true)
    renderNav()

    expect(
      screen.getByRole('button', { name: /switch to (dark|light) theme/i }),
    ).toBeInTheDocument()
  })
})

describe('TopNavigation routing', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const link = (name: string) => screen.getByRole('link', { name })

  it('Home goes to the Studio (not the landing page) and Training to its Configure view', () => {
    stubViewport(false)
    renderNav('/monitoring')

    expect(link('Home')).toHaveAttribute('href', '/studio')
    expect(link('Training')).toHaveAttribute('href', '/studio?view=training')
  })

  it('marks exactly one Studio view active', () => {
    stubViewport(false)
    renderNav('/studio')
    expect(link('Home')).toHaveAttribute('aria-current', 'page')
    expect(link('Training')).not.toHaveAttribute('aria-current')
  })

  it('marks Training active only on the training view', () => {
    stubViewport(false)
    renderNav('/studio?view=training')
    expect(link('Training')).toHaveAttribute('aria-current', 'page')
    expect(link('Home')).not.toHaveAttribute('aria-current')
  })

  it('keeps Monitoring active on nested paths and nothing active on the landing page', () => {
    stubViewport(false)
    renderNav('/reports/run-1')
    expect(link('Reports')).toHaveAttribute('aria-current', 'page')
    expect(link('Home')).not.toHaveAttribute('aria-current')
  })
})
