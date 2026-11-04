import { act, fireEvent, I18nextProvider } from 'react-i18next'
import i18n from '../i18n'
import { MemoryRouter } from 'react-router-dom'
import { act, beforeEach, describe, expect, it, vi } from 'vitest'
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

describe('landing page sections', () => {
  beforeEach(() => {
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
  afterEach(() => vi.unstubAllGlobals())

  it('keeps the existing hero exactly as it was', () => {
    renderHome()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'A safer sandbox for stronger agents.',
    )
    expect(screen.getByRole('link', { name: /Watch Demo/ })).toHaveAttribute('href', '/monitoring')
    for (const link of screen.getAllByRole('link', { name: /Open Studio/ })) {
      expect(link).toHaveAttribute('href', '/studio')
    }
    expect(screen.getByText(/Simulate/)).toBeInTheDocument() // the badge text is unchanged
  })

  it('places the new sections between the first screen and the overview, in order', () => {
    const { container } = renderHome()
    const order = ['.ls-first-screen', '#telemetry', '.ls-tech', '#overview']
    const positions = order.map((selector) => {
      const node = container.querySelector(selector)
      expect(node, selector).not.toBeNull()
      return node as Element
    })
    for (let i = 0; i < positions.length - 1; i += 1) {
      expect(
        positions[i].compareDocumentPosition(positions[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy()
    }
    expect(screen.getAllByText('Fault Detection')).toHaveLength(1) // the strip is not duplicated
  })

  it('presents the telemetry terminal as an illustration, never as a live feed', () => {
    renderHome()
    const section = screen.getByRole('region', { name: 'Live telemetry' })
    expect(within(section).getByText(/illustrative sample/i)).toBeInTheDocument()
    expect(within(section).getByText(/not a live feed/i)).toBeInTheDocument()
    expect(
      within(section).getByText('Real-time training and recovery signals from your agents.'),
    ).toBeInTheDocument()
    const log = within(section).getByLabelText('Illustrative training log')
    expect(log).toHaveTextContent('WarehouseNavigation-v0')
    expect(log).toHaveTextContent('Step 30000')
    expect(log).toHaveTextContent('Status: Healthy')
    // The waveform is decorative.
    expect(section.querySelector('.ls-wave')).toHaveAttribute('aria-hidden', 'true')
  })

  it('lists only the technologies the project actually depends on', () => {
    renderHome()
    const strip = screen.getByRole('region', { name: 'Technology stack' })
    expect(within(strip).getByText('Built with')).toBeInTheDocument()
    const names = within(strip)
      .getAllByRole('listitem')
      .map((item) => item.textContent)
    expect(names).toEqual(['Stable-Baselines3', 'PyTorch', 'Gymnasium', 'FastAPI'])
  })

  it('keeps the three cards, their copy and their destinations', () => {
    renderHome()
    expect(
      screen.getByRole('heading', { level: 2, name: 'From fault to verified recovery' }),
    ).toBeInTheDocument()
    const expected: Array<[string, string, string]> = [
      ['Fault detection', 'Open monitoring', '/monitoring'],
      ['Experience provenance', 'Open diagnosis', '/diagnosis-recovery'],
      ['Adaptive recovery', 'Open reports', '/reports'],
    ]
    for (const [title, linkName, href] of expected) {
      const card = screen.getByRole('heading', { level: 3, name: title }).closest('article')!
      // The decorative arrow is hidden from assistive tech, so the link keeps its name.
      expect(within(card).getByRole('link', { name: linkName })).toHaveAttribute('href', href)
      expect(card.querySelector('.ls-overview__icon')).toHaveAttribute('aria-hidden', 'true')
    }
  })

  it('sends the scroll hint to the first new section', () => {
    const { container } = renderHome()
    const target = container.querySelector('#telemetry') as HTMLElement
    const scrollIntoView = vi.fn()
    target.scrollIntoView = scrollIntoView
    fireEvent.click(screen.getByRole('button', { name: 'Scroll to overview' }))
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
  })
})

describe('scroll reveals', () => {
  type Callback = (entries: Array<{ isIntersecting: boolean }>) => void
  // Which callback watches which element (other components, like the particle scene, observe too).
  let watchers = new Map<Element, Callback>()
  const disconnect = vi.fn()
  const trigger = (element: Element, isIntersecting: boolean) =>
    act(() => watchers.get(element)?.([{ isIntersecting }]))

  beforeEach(() => {
    watchers = new Map()
    disconnect.mockClear()
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        private callback: Callback
        constructor(callback: Callback) {
          this.callback = callback
        }
        observe(element: Element) {
          watchers.set(element, this.callback)
        }
        disconnect = disconnect
      },
    )
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation(() => ({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('hides each new block until it scrolls into view, then reveals it once', () => {
    const { container } = renderHome()
    const revealables = [...container.querySelectorAll('[data-reveal]')]
    // Telemetry panel, technology strip and three cards.
    expect(revealables).toHaveLength(5)
    revealables.forEach((node) => expect(node).not.toHaveAttribute('data-in'))

    trigger(revealables[0], false)
    expect(revealables[0]).not.toHaveAttribute('data-in') // off screen: stays hidden

    trigger(revealables[0], true)
    expect(revealables[0]).toHaveAttribute('data-in')
    expect(disconnect).toHaveBeenCalled() // it plays once and stops observing
    expect(revealables[1]).not.toHaveAttribute('data-in') // the others wait for their own turn
  })

  it('staggers the cards by their position', () => {
    const { container } = renderHome()
    const cards = [...container.querySelectorAll<HTMLElement>('.ls-overview__card')]
    expect(cards.map((card) => card.style.getPropertyValue('--i'))).toEqual(['0', '1', '2'])
  })

  it('never leaves content hidden when IntersectionObserver is unavailable', () => {
    vi.stubGlobal('IntersectionObserver', undefined)
    const { container } = renderHome()
    container
      .querySelectorAll('[data-reveal]')
      .forEach((node) => expect(node).toHaveAttribute('data-in'))
  })
})
