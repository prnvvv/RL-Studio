import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EventTimeline, TimelineEvent } from './EventTimeline'

const events: TimelineEvent[] = [
  {
    id: 'evt_003',
    timestamp: '2026-10-25T12:04:09Z',
    category: 'recovery',
    title: 'Recovery execution completed',
    detail: 'Restored checkpoint ckpt_0007 and discarded pending rollout data.',
    source: 'recovery-worker',
  },
  {
    id: 'evt_002',
    timestamp: '2026-10-25T12:02:00Z',
    category: 'diagnosis',
    title: 'AI hypothesis returned',
    source: 'diagnosis-service',
  },
  {
    id: 'evt_001',
    timestamp: '2026-10-25T12:00:00Z',
    category: 'observation',
    title: 'Goal reward observed',
  },
]

describe('EventTimeline', () => {
  it('renders recorded events in the supplied order with UTC timestamps', () => {
    render(<EventTimeline events={events} />)

    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(3)

    expect(items[0]).toHaveTextContent('12:04:09Z')
    expect(items[1]).toHaveTextContent('12:02:00Z')
    expect(items[2]).toHaveTextContent('12:00:00Z')

    expect(screen.getByText('Recovery execution completed')).toBeInTheDocument()
    expect(screen.getByText('AI hypothesis returned')).toBeInTheDocument()
    expect(screen.getByText('Goal reward observed')).toBeInTheDocument()
  })

  it('labels every category in text, not by colour alone', () => {
    render(<EventTimeline events={events} />)

    expect(screen.getByText('Recovery')).toBeInTheDocument()
    expect(screen.getByText('Diagnosis')).toBeInTheDocument()
    expect(screen.getByText('Observation')).toBeInTheDocument()
  })

  it('renders an unclassified backend event safely instead of guessing a category', () => {
    render(
      <EventTimeline
        events={[
          {
            id: 'evt_unknown',
            timestamp: '2026-10-25T12:05:00Z',
            category: 'unknown',
            title: 'Event type not mapped',
          },
        ]}
      />,
    )

    expect(screen.getByText('Unclassified')).toBeInTheDocument()
    expect(screen.getByText('Event type not mapped')).toBeInTheDocument()
  })

  it('states when only a bounded window of a larger history is shown', () => {
    render(<EventTimeline events={events} totalCount={42} />)

    expect(screen.getByText('Showing 3 of 42 recorded events.')).toBeInTheDocument()
  })

  it('renders nothing for an empty event list so the page can own the empty state', () => {
    const { container } = render(<EventTimeline events={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
