import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RequirementStatusBadge } from './RequirementStatusBadge'

describe('RequirementStatusBadge', () => {
  it('labels each review state explicitly', () => {
    const { rerender } = render(<RequirementStatusBadge state="draft" />)
    expect(screen.getByText('Draft — awaiting review')).toBeInTheDocument()

    rerender(<RequirementStatusBadge state="confirmed" />)
    expect(screen.getByText('Confirmed for this session')).toBeInTheDocument()

    rerender(<RequirementStatusBadge state="rejected" />)
    expect(screen.getByText('Rejected')).toBeInTheDocument()
  })
})
