import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LoadingSkeleton } from './LoadingSkeleton'

describe('LoadingSkeleton', () => {
  it('announces the pending state accessibly with the default row count', () => {
    const { container } = render(<LoadingSkeleton />)
    expect(screen.getByRole('status', { name: 'Loading data' })).toBeInTheDocument()
    expect(container.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(3)
  })

  it('renders the requested number of bars', () => {
    const { container } = render(<LoadingSkeleton rows={5} />)
    expect(container.querySelectorAll('span[aria-hidden="true"]')).toHaveLength(5)
  })
})
