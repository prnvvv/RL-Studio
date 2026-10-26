import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ExpandableSection } from './ExpandableSection'

describe('ExpandableSection', () => {
  it('starts collapsed and exposes the trigger state to assistive technology', () => {
    render(
      <ExpandableSection title="Evidence Used" summary="Not available.">
        <p>Evidence body</p>
      </ExpandableSection>,
    )

    const trigger = screen.getByRole('button', { name: /Evidence Used/ })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('Not available.')).toBeInTheDocument()
    expect(screen.queryByText('Evidence body')).not.toBeInTheDocument()
  })

  it('opens and closes on activation, keeping content associated with the trigger', () => {
    render(
      <ExpandableSection title="Analysis Details">
        <p>Analysis body</p>
      </ExpandableSection>,
    )

    const trigger = screen.getByRole('button', { name: /Analysis Details/ })
    fireEvent.click(trigger)

    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    const region = screen.getByRole('region', { name: /Analysis Details/ })
    expect(region).toHaveTextContent('Analysis body')

    fireEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Analysis body')).not.toBeInTheDocument()
  })

  it('uses a native button so Enter and Space work without custom key handling', () => {
    render(
      <ExpandableSection title="Recommended Recovery Plan">
        <p>Plan body</p>
      </ExpandableSection>,
    )

    const trigger = screen.getByRole('button', { name: /Recommended Recovery Plan/ })
    // A native button with an explicit type is required: it is focusable and
    // activates on Enter/Space from the platform, and cannot submit a form.
    expect(trigger.tagName).toBe('BUTTON')
    expect(trigger).toHaveAttribute('type', 'button')
    expect(trigger).not.toHaveAttribute('tabindex', '-1')

    // The disclosure region is announced with the trigger's own text as its name.
    expect(trigger).toHaveAttribute('aria-controls')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })
})
