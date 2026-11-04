import { I18nextProvider } from 'react-i18next'
import { i18n } from '../i18n'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HomePage } from './HomePage'

function renderHome() {
  return render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter initialEntries={['/']}>
        <HomePage />
      </MemoryRouter>
    </I18nextProvider>,
  )
}

describe('HomePage (landing)', () => {
  beforeEach(() => {
    // jsdom has no WebGL or matchMedia; the scene must degrade silently.
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

  it('renders the headline as the single h1', () => {
    renderHome()
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading).toHaveTextContent('A safer sandbox for stronger agents.')
  })

  it('offers the Open Studio and Watch Demo calls to action', () => {
    renderHome()
    const openLinks = screen.getAllByRole('link', { name: /Open Studio/ })
    expect(openLinks.length).toBeGreaterThanOrEqual(2)
    openLinks.forEach((link) => expect(link).toHaveAttribute('href', '/studio'))
    expect(screen.getByRole('link', { name: /Watch Demo/ })).toBeInTheDocument()
  })

  it('shows the three capability labels and an accessible scroll hint', () => {
    renderHome()
    expect(screen.getAllByText('Fault Detection').length).toBeGreaterThan(0)
    expect(screen.getByText('Experience Provenance')).toBeInTheDocument()
    expect(screen.getByText('Adaptive Recovery')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Scroll to overview' })).toBeInTheDocument()
  })

  it('keeps the particle scene decorative and survives missing WebGL', () => {
    const { container } = renderHome()
    const scene = container.querySelector('.ls-scene')
    expect(scene).toHaveAttribute('aria-hidden', 'true')
    // No WebGL in jsdom: the canvas is dropped rather than left blank.
    expect(scene?.querySelector('canvas')).toBeNull()
  })
})
