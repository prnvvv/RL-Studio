import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { addToast, MAX_TOASTS, ToastProvider, useToast, type ToastItem, type ToastTone } from './toast'

function Trigger({ tone = 'success', message = 'Training started' }: { tone?: ToastTone; message?: string }) {
  const toast = useToast()
  return (
    <button type="button" onClick={() => toast.push(tone, message)}>
      go
    </button>
  )
}

describe('addToast', () => {
  const item = (id: number, message = `m${id}`): ToastItem => ({ id, tone: 'info', message })

  it('keeps only the newest toasts', () => {
    let items: ToastItem[] = []
    for (let i = 1; i <= MAX_TOASTS + 2; i += 1) items = addToast(items, item(i))
    expect(items).toHaveLength(MAX_TOASTS)
    expect(items[items.length - 1].id).toBe(MAX_TOASTS + 2)
  })

  it('collapses an identical consecutive message instead of stacking it', () => {
    const items = addToast([item(1, 'same')], item(2, 'same'))
    expect(items.map((t) => t.id)).toEqual([2])
  })
})

describe('ToastProvider', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('shows a toast, announces errors assertively, and dismisses on demand or after a delay', () => {
    render(
      <ToastProvider>
        <Trigger tone="error" message="Failed to connect" />
      </ToastProvider>,
    )
    fireEvent.click(screen.getByText('go'))
    expect(screen.getByRole('alert')).toHaveTextContent('Failed to connect')
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss notification' }))
    expect(screen.queryByRole('alert')).toBeNull()

    fireEvent.click(screen.getByText('go'))
    act(() => {
      vi.advanceTimersByTime(9000)
    })
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('uses a polite status role for non-errors', () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    )
    fireEvent.click(screen.getByText('go'))
    expect(screen.getByRole('status')).toHaveTextContent('Training started')
  })
})
