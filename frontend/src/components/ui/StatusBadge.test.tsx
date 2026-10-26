import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge } from './StatusBadge'

describe('StatusBadge', () => {
  it('always renders its status as text', () => {
    render(<StatusBadge label="Confirmed violation" glyph="check" />)

    expect(screen.getByText('Confirmed violation')).toBeInTheDocument()
  })

  it('exposes its tone so meaning is not conveyed by brightness alone', () => {
    const { rerender } = render(<StatusBadge label="AI hypothesis" tone="quiet" glyph="query" />)
    expect(screen.getByText('AI hypothesis').closest('[data-tone]')).toHaveAttribute(
      'data-tone',
      'quiet',
    )

    rerender(<StatusBadge label="Validated conclusion" tone="strong" glyph="check" />)
    expect(screen.getByText('Validated conclusion').closest('[data-tone]')).toHaveAttribute(
      'data-tone',
      'strong',
    )
  })

  it('supports a qualifier note such as an estimate disclaimer', () => {
    render(<StatusBadge label="Provider estimate" tone="quiet" note="not calibrated" />)

    expect(screen.getByText('not calibrated')).toBeInTheDocument()
  })
})
