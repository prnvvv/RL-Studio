import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { formatUtcTime } from '../../utils/datetime'
import { StaleDataNotice } from './StaleDataNotice'

describe('StaleDataNotice', () => {
  it('states which data may be out of date', () => {
    render(<StaleDataNotice subject="training stats" />)
    expect(screen.getByRole('status').textContent).toContain('training stats may be out of date')
  })

  it('falls back to a generic label without a subject', () => {
    render(<StaleDataNotice />)
    expect(screen.getByRole('status').textContent).toContain('Displayed data may be out of date')
  })

  it('shows the recorded time when provided', () => {
    render(<StaleDataNotice asOf={formatUtcTime('2026-11-01T12:04:09Z') ?? undefined} />)
    expect(screen.getByRole('status').textContent).toContain('as of')
    expect(screen.getByRole('status').textContent).toContain('12:04:09Z')
  })
})
