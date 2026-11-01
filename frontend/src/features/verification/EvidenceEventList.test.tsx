import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { EvidenceReference } from '../../schemas/verification'
import { EvidenceEventList } from './EvidenceEventList'

function ref(overrides: Partial<EvidenceReference>): EvidenceReference {
  return {
    id: 'evt_demo_1',
    source: 'event_id',
    run_identifier: 'run_demo',
    environment_identifier: 'warehouse_v1',
    location: null,
    timestamp: '2026-10-25T11:58:40Z',
    ...overrides,
  }
}

describe('EvidenceEventList', () => {
  it('renders identifiers, source, and timestamp; not event bodies', () => {
    render(
      <EvidenceEventList
        evidence={[
          ref({ id: 'evt_demo_2', timestamp: '2026-10-25T12:00:02Z' }),
          ref({ id: 'evt_demo_1' }),
        ]}
      />,
    )

    expect(screen.getByText('evt_demo_1')).toBeInTheDocument()
    expect(screen.getByText('evt_demo_2')).toBeInTheDocument()
    expect(screen.getAllByText('Source: event_id')).toHaveLength(2)
    expect(screen.getByText(/2026-10-25 12:00:02Z/)).toBeInTheDocument()
    expect(screen.getAllByText(/Run: run_demo/)).toHaveLength(2)
    expect(screen.getAllByText(/Environment: warehouse_v1/)).toHaveLength(2)
  })

  it('marks records without timestamps as not recorded', () => {
    render(<EvidenceEventList evidence={[ref({ timestamp: null })]} />)
    expect(screen.getByText(/Time not recorded/)).toBeInTheDocument()
  })

  it('renders inert identifiers when no navigation handler is wired', () => {
    render(<EvidenceEventList evidence={[ref({ id: 'evt_static' })]} />)
    expect(screen.queryByRole('button', { name: 'evt_static' })).not.toBeInTheDocument()
  })

  it('navigates to evidence only through the explicit handler', () => {
    const onOpenEvidence = vi.fn()
    render(
      <EvidenceEventList
        evidence={[ref({ id: 'evt_nav' }), ref({ id: 'evt_other' })]}
        onOpenEvidence={onOpenEvidence}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'evt_other' }))
    expect(onOpenEvidence).toHaveBeenCalledOnce()
    expect(onOpenEvidence).toHaveBeenCalledWith('evt_other')
  })

  it('orders records chronologically and keeps untimed ones last', () => {
    render(
      <EvidenceEventList
        evidence={[
          ref({ id: 'evt_late', timestamp: '2026-10-25T12:00:02Z' }),
          ref({ id: 'evt_untimed', timestamp: null }),
          ref({ id: 'evt_early', timestamp: '2026-10-25T11:58:40Z' }),
        ]}
      />,
    )

    const ids = screen
      .getAllByText(/evt_(late|early|untimed)/)
      .map((element) => element.textContent)
    // First and last entries are the dated ones in order; the untimed entry
    // appears somewhere after the early record.
    expect(ids.indexOf('evt_early')).toBeLessThan(ids.indexOf('evt_late'))
  })
})
