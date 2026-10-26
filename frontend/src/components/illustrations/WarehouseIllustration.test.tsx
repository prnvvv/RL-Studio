import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WarehouseIllustration } from './WarehouseIllustration'

describe('WarehouseIllustration', () => {
  it('is announced as an illustration preview rather than a simulation', () => {
    render(<WarehouseIllustration />)

    const illustration = screen.getByRole('img')
    expect(illustration).toHaveAccessibleName(/illustration preview/i)
    expect(illustration).toHaveAccessibleName(/not a running simulation/i)
  })
})
