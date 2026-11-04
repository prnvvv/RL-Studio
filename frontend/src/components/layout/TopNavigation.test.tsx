import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ActiveProjectProvider } from '../../contexts/ActiveProjectContext'
import { ThemeProvider } from '../../contexts/ThemeContext'
import { TopNavigation } from './TopNavigation'

const ALL_DESTINATIONS = [
  'Projects',
  'Studio',
  'Monitoring',
  'Reports',
  'Diagnosis & Recovery',
  'Settings',
]

/** Destinations that were removed from the navigation and must not come back as links. */
const REMOVED_DESTINATIONS = ['Home', 'Training', 'Environments']

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
    expect(screen.getByRole('link', { name: 'Studio' })).toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.queryByRole('link', { name: 'Studio' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open navigation menu' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
  })

  it('dismisses the menu after choosing a destination from it', () => {
    stubViewport(true)
    renderNav()

    fireEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }))
    fireEvent.click(screen.getByRole('link', { name: 'Studio' }))

    expect(screen.queryByRole('link', { name: 'Studio' })).not.toBeInTheDocument()
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

  it('has one permanent Projects entry that goes to /projects', () => {
    stubViewport(false)
    renderNav('/monitoring')
    expect(screen.getAllByRole('link', { name: 'Projects' })).toHaveLength(1)
    expect(link('Projects')).toHaveAttribute('href', '/projects')
  })

  it('highlights Projects on the dashboard and on a project workspace, and nowhere else', () => {
    stubViewport(false)
    for (const path of ['/projects', '/projects/prj_0123456789abcdef']) {
      const view = render(
        <ThemeProvider>
          <MemoryRouter initialEntries={[path]}>
            <TopNavigation />
          </MemoryRouter>
        </ThemeProvider>,
      )
      expect(link('Projects')).toHaveAttribute('aria-current', 'page')
      expect(screen.getAllByRole('link', { current: 'page' })).toHaveLength(1)
      view.unmount()
    }
    renderNav('/studio')
    expect(link('Projects')).not.toHaveAttribute('aria-current')
  })

  it('shows Projects on every existing page, in both layouts, with and without an active project', () => {
    const pages = [
      '/studio',
      '/studio?view=training',
      '/monitoring',
      '/reports',
      '/reports/run-1',
      '/diagnosis-recovery',
      '/settings',
      '/projects',
    ]
    for (const active of [false, true]) {
      if (active) window.localStorage.setItem('rl-studio.activeProject', 'prj_0123456789abcdef')
      else window.localStorage.clear()
      vi.stubGlobal(
        'fetch',
        vi.fn(
          async () =>
            new Response(JSON.stringify({ project_id: 'prj_0123456789abcdef', name: 'Alpha' }), {
              status: 200,
            }),
        ),
      )
      for (const narrow of [false, true]) {
        stubViewport(narrow)
        for (const path of pages) {
          const view = render(
            <ThemeProvider>
              <ActiveProjectProvider>
                <MemoryRouter initialEntries={[path]}>
                  <TopNavigation />
                </MemoryRouter>
              </ActiveProjectProvider>
            </ThemeProvider>,
          )
          if (narrow) fireEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }))
          expect(screen.getAllByRole('link', { name: 'Projects' })).toHaveLength(1)
          expect(screen.getByRole('link', { name: 'Projects' })).toHaveAttribute(
            'href',
            '/projects',
          )
          view.unmount()
        }
      }
    }
    window.localStorage.clear()
  })

  it('keeps the active-project chip alongside Projects without duplicating either', async () => {
    window.localStorage.setItem('rl-studio.activeProject', 'prj_0123456789abcdef')
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ project_id: 'prj_0123456789abcdef', name: 'Alpha' }), {
            status: 200,
          }),
      ),
    )
    stubViewport(false)
    render(
      <ThemeProvider>
        <ActiveProjectProvider>
          <MemoryRouter initialEntries={['/studio']}>
            <TopNavigation />
          </MemoryRouter>
        </ActiveProjectProvider>
      </ThemeProvider>,
    )
    expect(await screen.findByRole('link', { name: 'Active project: Alpha' })).toHaveAttribute(
      'href',
      '/projects/prj_0123456789abcdef',
    )
    expect(screen.getAllByRole('link', { name: 'Projects' })).toHaveLength(1)
    window.localStorage.clear()
  })
  it('has exactly one Studio entry, pointing at the Studio workspace', () => {
    stubViewport(false)
    renderNav('/monitoring')

    expect(screen.getAllByRole('link', { name: 'Studio' })).toHaveLength(1)
    expect(link('Studio')).toHaveAttribute('href', '/studio')
  })

  it('no longer offers Home, Training or Environments as navigation', () => {
    for (const narrow of [false, true]) {
      stubViewport(narrow)
      const view = render(
        <ThemeProvider>
          <MemoryRouter initialEntries={['/']}>
            <TopNavigation />
          </MemoryRouter>
        </ThemeProvider>,
      )
      if (narrow) fireEvent.click(screen.getByRole('button', { name: 'Open navigation menu' }))
      for (const label of REMOVED_DESTINATIONS) {
        expect(screen.queryByRole('link', { name: label })).not.toBeInTheDocument()
      }
      view.unmount()
    }
  })

  it('orders the left group Projects, Studio, Monitoring, Reports, Diagnosis & Recovery and keeps Settings on the right', () => {
    stubViewport(false)
    renderNav('/')

    const primary = within(screen.getByRole('navigation', { name: 'Primary' }))
      .getAllByRole('link')
      .map((a) => a.textContent)
    expect(primary).toEqual(['Projects', 'Studio', 'Monitoring', 'Reports', 'Diagnosis & Recovery'])
    expect(screen.getByRole('link', { name: 'Settings' })).toBeInTheDocument()
    expect(
      within(screen.getByRole('navigation', { name: 'Primary' })).queryByRole('link', {
        name: 'Settings',
      }),
    ).toBeNull()
  })

  it('keeps Diagnosis & Recovery on its existing route', () => {
    stubViewport(false)
    renderNav('/')
    expect(link('Diagnosis & Recovery')).toHaveAttribute('href', '/diagnosis-recovery')
  })

  it('marks Studio active on /studio whatever its view query', () => {
    stubViewport(false)
    for (const path of ['/studio', '/studio?view=training']) {
      const view = render(
        <ThemeProvider>
          <MemoryRouter initialEntries={[path]}>
            <TopNavigation />
          </MemoryRouter>
        </ThemeProvider>,
      )
      expect(link('Studio')).toHaveAttribute('aria-current', 'page')
      expect(screen.getAllByRole('link', { current: 'page' })).toHaveLength(1)
      view.unmount()
    }
  })

  it('marks Diagnosis & Recovery active on its route, and only it', () => {
    stubViewport(false)
    renderNav('/diagnosis-recovery')
    expect(link('Diagnosis & Recovery')).toHaveAttribute('aria-current', 'page')
    expect(link('Studio')).not.toHaveAttribute('aria-current')
  })

  it('keeps Reports active on nested paths and marks nothing active on the landing page', () => {
    stubViewport(false)
    renderNav('/reports/run-1')
    expect(link('Reports')).toHaveAttribute('aria-current', 'page')
    expect(link('Studio')).not.toHaveAttribute('aria-current')
  })
  it('shows the active project chip with a link to its workspace, on any page, in both layouts', async () => {
    window.localStorage.setItem('rl-studio.activeProject', 'prj_0123456789abcdef')
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ project_id: 'prj_0123456789abcdef', name: 'Alpha' }), {
            status: 200,
          }),
      ),
    )
    for (const narrow of [false, true]) {
      stubViewport(narrow)
      const view = render(
        <ThemeProvider>
          <ActiveProjectProvider>
            <MemoryRouter initialEntries={['/monitoring']}>
              <TopNavigation />
            </MemoryRouter>
          </ActiveProjectProvider>
        </ThemeProvider>,
      )
      const chip = await screen.findByRole('link', { name: 'Active project: Alpha' })
      expect(chip).toHaveAttribute('href', '/projects/prj_0123456789abcdef')
      view.unmount()
    }
    window.localStorage.clear()
  })
})
