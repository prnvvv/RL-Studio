import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'
import { MonitoringPage } from './MonitoringPage'

/**
 * Minimal WebSocket stand-in. The page's real transport is the WebSocket
 * stream, so tests must supply a deterministic socket rather than letting
 * jsdom open (or fail to open) a real connection.
 */
class FakeSocket {
  static instances: FakeSocket[] = []

  readonly url: string
  onopen: (() => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null
  onerror: ((event: unknown) => void) | null = null
  onclose: ((event: unknown) => void) | null = null
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    FakeSocket.instances.push(this)
  }
}

function renderPage(initialEntry = '/monitoring') {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <MonitoringPage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

function frame(overrides: Record<string, unknown> = {}): string {
  return JSON.stringify({
    event_id: 'evt_1',
    event_type: 'reward_observed',
    run_id: 'run_1',
    episode_id: 'episode_3',
    timestep: 1200,
    actual_reward: 25,
    timestamp: '2026-10-25T12:00:00Z',
    ...overrides,
  })
}

function recentEvents() {
  return screen.getByRole('region', { name: 'Recent Events' })
}

beforeEach(() => {
  FakeSocket.instances = []
  vi.stubGlobal('WebSocket', FakeSocket)
  // The status endpoint is read for a scoped run; answer with a real payload
  // so the page renders a backend-reported lifecycle rather than a failure.
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(JSON.stringify({ run_id: 'run_1', status: 'running' }), { status: 200 }),
    ),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('MonitoringPage', () => {
  it('shows both principal areas with Recent Events first in reading order', () => {
    renderPage()

    const recentEventsSection = screen.getByRole('region', { name: 'Recent Events' })
    const liveStats = screen.getByRole('region', { name: 'Live Stats' })

    expect(recentEventsSection).toBeInTheDocument()
    expect(liveStats).toBeInTheDocument()

    // Recent Events must precede Live Stats in DOM order.
    expect(recentEventsSection.compareDocumentPosition(liveStats)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    )
  })

  it('asks for a run scope instead of inventing an event timeline', () => {
    renderPage()

    expect(screen.getByText('No run selected')).toBeInTheDocument()
    expect(within(recentEvents()).queryAllByRole('listitem')).toHaveLength(0)
  })

  it('does not render a View All control when no event history exists', () => {
    renderPage()

    expect(screen.queryByRole('button', { name: 'View All' })).not.toBeInTheDocument()
  })

  it('states that live updates are not configured without a run', () => {
    renderPage()

    expect(screen.getByRole('status', { name: 'Live update connection status' })).toHaveTextContent(
      'Live updates not configured',
    )
    // No run means no connection is attempted at all.
    expect(FakeSocket.instances).toHaveLength(0)
  })

  it('keeps comparison charts secondary and empty rather than fabricated', () => {
    renderPage()

    expect(screen.getByRole('region', { name: 'Comparison Charts' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /no data recorded/i })).toBeInTheDocument()
  })

  it('opens exactly one live subscription scoped to the selected run', () => {
    renderPage('/monitoring?runId=run_1')

    expect(FakeSocket.instances).toHaveLength(1)
    expect(FakeSocket.instances[0].url).toContain('/api/v1/events/run_1')
    expect(screen.getByRole('status', { name: 'Live update connection status' })).toHaveTextContent(
      'Connecting',
    )
  })

  it('renders backend-reported events and suppresses a replayed duplicate', () => {
    renderPage('/monitoring?runId=run_1')
    const socket = FakeSocket.instances[0]

    act(() => {
      socket.onopen?.()
    })
    expect(screen.getByRole('status', { name: 'Live update connection status' })).toHaveTextContent(
      'Live',
    )

    act(() => {
      socket.onmessage?.({ data: frame() })
    })

    const items = within(recentEvents()).getAllByRole('listitem')
    expect(items).toHaveLength(1)
    // The event type is shown verbatim; categories are not guessed.
    expect(within(items[0]).getByText('reward_observed')).toBeInTheDocument()
    expect(within(items[0]).getByText('Unclassified')).toBeInTheDocument()
    expect(recentEvents()).toHaveTextContent('Live window: 1 event')

    // A reconnect replays recent events; the same event id must not duplicate.
    act(() => {
      socket.onmessage?.({ data: frame() })
    })
    expect(within(recentEvents()).getAllByRole('listitem')).toHaveLength(1)
  })

  it('drops a malformed frame instead of rendering guessed event data', () => {
    renderPage('/monitoring?runId=run_1')
    const socket = FakeSocket.instances[0]

    act(() => {
      socket.onmessage?.({ data: JSON.stringify({ event_id: 'evt_bad' }) })
      socket.onmessage?.({ data: 'not json' })
    })

    expect(within(recentEvents()).queryAllByRole('listitem')).toHaveLength(0)
    expect(screen.getByText('No events recorded for this scope')).toBeInTheDocument()
  })

  it('renders the backend-reported lifecycle for the scoped run', async () => {
    renderPage('/monitoring?runId=run_1')

    await waitFor(() => expect(screen.getByText('Running')).toBeInTheDocument())
    expect(screen.getByText('Reported status')).toBeInTheDocument()
    // The run lifecycle panel reads the same scope as the event stream.
    expect(screen.getByText('Status read at')).toBeInTheDocument()
  })

  it('carries incident scope without loading an incident record here', () => {
    renderPage('/monitoring?runId=run_1&incidentId=inc_2')

    expect(screen.getByText('inc_2')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'open the incident record' })).toHaveAttribute(
      'href',
      '/diagnosis-recovery?incidentId=inc_2',
    )
  })

  it('keeps the selected run and incident scope in related links', () => {
    renderPage('/monitoring?runId=run_1&incidentId=inc_2')

    // Scoped to the panel: the application shell also has a "Reports" link.
    const related = within(screen.getByRole('region', { name: 'Related views' }))
    expect(related.getByRole('link', { name: 'Training dashboard' })).toHaveAttribute(
      'href',
      '/training?runId=run_1',
    )
    expect(related.getByRole('link', { name: 'Reports' })).toHaveAttribute(
      'href',
      '/reports?incidentId=inc_2',
    )
  })

  it('closes the subscription and clears events when the run scope is cleared', async () => {
    renderPage('/monitoring?runId=run_1')
    const socket = FakeSocket.instances[0]

    act(() => {
      socket.onmessage?.({ data: frame() })
    })
    expect(within(recentEvents()).getAllByRole('listitem')).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: 'Clear run scope' }))

    expect(socket.close).toHaveBeenCalled()
    await waitFor(() => expect(screen.getByText('No run selected')).toBeInTheDocument())
    expect(within(recentEvents()).queryAllByRole('listitem')).toHaveLength(0)
  })
})
