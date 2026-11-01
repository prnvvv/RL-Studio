import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ErrorState } from './ErrorState'

describe('ErrorState', () => {
  it('announces the failure with the provided title and description', () => {
    render(
      <ErrorState title="Request failed" description="The service is currently unavailable." />,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('Request failed')).toBeInTheDocument()
    expect(screen.getByText('The service is currently unavailable.')).toBeInTheDocument()
  })

  it('offers the retry affordance only when provided', () => {
    const onRetry = vi.fn()
    const { rerender } = render(
      <ErrorState title="Request failed" description="Timeout reached." />,
    )
    expect(screen.queryByRole('button')).not.toBeInTheDocument()

    rerender(
      <ErrorState
        title="Request failed"
        description="Timeout reached."
        action={
          <button type="button" onClick={onRetry}>
            Try again
          </button>
        }
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
