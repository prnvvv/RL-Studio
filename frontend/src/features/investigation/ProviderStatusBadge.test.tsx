import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ProviderStatusBadge } from './ProviderStatusBadge'
import type { InvestigationState } from '../../schemas/investigation'

const STATES: InvestigationState[] = ['no_record', 'completed', 'provider_unavailable', 'failed']

describe('ProviderStatusBadge', () => {
  it('labels each investigation state explicitly', () => {
    for (const state of STATES) {
      const { unmount } = render(<ProviderStatusBadge state={state} />)
      if (state === 'no_record')
        expect(screen.getByText('No investigation recorded')).toBeInTheDocument()
      if (state === 'completed')
        expect(screen.getByText('Investigation completed')).toBeInTheDocument()
      if (state === 'provider_unavailable')
        expect(screen.getByText('Provider unavailable')).toBeInTheDocument()
      if (state === 'failed') expect(screen.getByText('Investigation failed')).toBeInTheDocument()
      unmount()
    }
  })

  it('never presents a failed state as a completed analysis', () => {
    render(<ProviderStatusBadge state="failed" />)
    expect(screen.queryByText('Investigation completed')).not.toBeInTheDocument()
  })
})
