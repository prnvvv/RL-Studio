import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '../contexts/ThemeContext'
import { MonitoringPage } from './MonitoringPage'

function renderPage() {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={['/monitoring']}>
        <MonitoringPage />
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('MonitoringPage', () => {
  it('shows both principal areas with Recent Events first in reading order', () => {
    renderPage()

    const recentEvents = screen.getByRole('region', { name: 'Recent Events' })
    const liveStats = screen.getByRole('region', { name: 'Live Stats' })

    expect(recentEvents).toBeInTheDocument()
    expect(liveStats).toBeInTheDocument()

    // Recent Events must precede Live Stats in DOM order.
    expect(recentEvents.compareDocumentPosition(liveStats)).toBe(Node.DOCUMENT_POSITION_FOLLOWING)
  })

  it('reports no recorded events instead of inventing a timeline', () => {
    renderPage()

    expect(screen.getByText('No events recorded for this scope')).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('does not expose a working View All control without a history source', () => {
    renderPage()

    expect(screen.getByRole('button', { name: 'View All' })).toBeDisabled()
  })

  it('states that live updates are not configured', () => {
    renderPage()

    expect(screen.getByRole('status', { name: 'Live update connection status' })).toHaveTextContent(
      'Live updates not configured',
    )
  })

  it('keeps comparison charts secondary and empty rather than fabricated', () => {
    renderPage()

    expect(screen.getByRole('region', { name: 'Comparison Charts' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /no data recorded/i })).toBeInTheDocument()
  })
})
