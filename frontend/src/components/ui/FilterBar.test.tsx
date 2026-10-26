import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { FilterBar } from './FilterBar'

describe('FilterBar', () => {
  it('associates a visible label with the search field', () => {
    render(
      <FilterBar
        label="Filter runs"
        value=""
        onChange={() => {}}
        onReset={() => {}}
        summary="0 of 0 recorded runs shown."
      />,
    )

    const input = screen.getByLabelText('Filter runs')
    expect(input).toHaveAttribute('type', 'search')
    expect(input).not.toBeDisabled()
  })

  it('reports each change to the caller and announces the result summary', () => {
    const onChange = vi.fn()
    render(
      <FilterBar
        label="Filter runs"
        value=""
        onChange={onChange}
        onReset={() => {}}
        summary="0 of 0 recorded runs shown."
      />,
    )

    fireEvent.change(screen.getByLabelText('Filter runs'), { target: { value: 'warehouse' } })

    expect(onChange).toHaveBeenCalledWith('warehouse')
    expect(screen.getByRole('status', { name: 'Filter results' })).toHaveTextContent(
      '0 of 0 recorded runs shown.',
    )
  })

  it('shows a reset action only while a filter is active, and resets it', () => {
    const onReset = vi.fn()
    const { rerender } = render(
      <FilterBar
        label="Filter runs"
        value=""
        onChange={() => {}}
        onReset={onReset}
        summary="3 of 3"
      />,
    )
    expect(screen.queryByRole('button', { name: 'Clear filter' })).not.toBeInTheDocument()

    rerender(
      <FilterBar
        label="Filter runs"
        value="warehouse"
        onChange={() => {}}
        onReset={onReset}
        summary="1 of 3"
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }))

    expect(onReset).toHaveBeenCalledTimes(1)
  })

  it('disables the control with a stated reason when there is nothing to filter', () => {
    render(
      <FilterBar
        label="Filter runs"
        value=""
        onChange={() => {}}
        onReset={() => {}}
        summary="0 of 0"
        disabled
        disabledReason="No run records are loaded, so there is nothing to filter."
      />,
    )

    expect(screen.getByLabelText('Filter runs')).toBeDisabled()
    expect(screen.getByRole('status', { name: 'Filter results' })).toHaveTextContent(
      'No run records are loaded, so there is nothing to filter.',
    )
    expect(screen.queryByRole('button', { name: 'Clear filter' })).not.toBeInTheDocument()
  })

  it('is exposed as a search landmark and does not reload the page on submit', () => {
    render(
      <FilterBar
        label="Filter runs"
        value="x"
        onChange={() => {}}
        onReset={() => {}}
        summary="1 of 1"
      />,
    )

    const form = screen.getByRole('search', { name: 'Filter runs controls' })
    const submit = new Event('submit', { bubbles: true, cancelable: true })
    form.dispatchEvent(submit)

    expect(submit.defaultPrevented).toBe(true)
  })
})
