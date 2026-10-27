import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LiveConnectionStatus } from './LiveConnectionStatus'

describe('LiveConnectionStatus', () => {
  it('does not claim a live connection when no transport is configured', () => {
    render(<LiveConnectionStatus state="not_configured" />)

    expect(screen.getByRole('status')).toHaveTextContent('Live updates not configured')
    expect(screen.queryByText('Live')).not.toBeInTheDocument()
  })

  it('reports a dropped connection without implying the run failed', () => {
    render(<LiveConnectionStatus state="disconnected" />)

    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Disconnected')
    expect(status).toHaveTextContent(/Training status is unchanged/)
    expect(status).not.toHaveTextContent(/failed/i)
  })

  it('shows the last snapshot time when supplied', () => {
    render(<LiveConnectionStatus state="stale" lastUpdated="12:04:09Z" />)

    expect(screen.getByRole('status')).toHaveTextContent('Last snapshot 12:04:09Z')
  })
})
