import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThemeProvider } from '../../contexts/ThemeContext'
import { ReportSection } from './ReportSection'

function renderSection(status: Parameters<typeof ReportSection>[0]['status']) {
  render(
    <ThemeProvider>
      <ReportSection title="Example section" description="Example description" status={status}>
        <p>Loaded content</p>
      </ReportSection>
    </ThemeProvider>,
  )
}

describe('ReportSection', () => {
  it('shows a loading placeholder for pending without rendering children', () => {
    renderSection({ kind: 'pending' })

    expect(screen.getByRole('status', { name: 'Loading data' })).toBeInTheDocument()
    expect(screen.queryByText('Loaded content')).not.toBeInTheDocument()
  })

  it('states not applicable with its reason, distinct from a failure', () => {
    renderSection({ kind: 'not_applicable', description: 'No incident is connected to this run.' })

    expect(screen.getByText('Not applicable to this run')).toBeInTheDocument()
    expect(screen.getByText('No incident is connected to this run.')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.queryByText('Loaded content')).not.toBeInTheDocument()
  })

  it('states unavailable with its reason and owner, distinct from not applicable', () => {
    renderSection({
      kind: 'unavailable',
      description: 'The backend does not scope this capability by run yet.',
      owner: 'Person 3 — run-scoped requirements contract',
    })

    expect(screen.getByText('Section unavailable')).toBeInTheDocument()
    expect(
      screen.getByText('The backend does not scope this capability by run yet.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/Required from: Person 3/)).toBeInTheDocument()
    expect(screen.queryByText('Loaded content')).not.toBeInTheDocument()
  })

  it('shows a retryable failure and invokes onRetry from its action', () => {
    const onRetry = vi.fn()
    renderSection({ kind: 'failed', description: 'The request timed out.', onRetry })

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('This section could not be loaded')).toBeInTheDocument()
    expect(screen.getByText('The request timed out.')).toBeInTheDocument()
    screen.getByRole('button', { name: 'Retry' }).click()
    expect(onRetry).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Loaded content')).not.toBeInTheDocument()
  })

  it('omits the retry action when no retry handler is supplied', () => {
    renderSection({ kind: 'failed', description: 'The request timed out.' })

    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })

  it('renders the section content only on success', () => {
    renderSection({ kind: 'success' })

    expect(screen.getByText('Loaded content')).toBeInTheDocument()
    expect(screen.queryByText('Section unavailable')).not.toBeInTheDocument()
    expect(screen.queryByText('Not applicable to this run')).not.toBeInTheDocument()
  })

  it('labels the panel header with the section title and description', () => {
    renderSection({ kind: 'success' })

    expect(screen.getByRole('region', { name: 'Example section' })).toBeInTheDocument()
    expect(screen.getByText('Example description')).toBeInTheDocument()
  })
})
