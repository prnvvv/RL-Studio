import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmationDialog } from './ConfirmationDialog'

describe('ConfirmationDialog', () => {
  it('renders a labelled modal dialog with cancel focused by default', () => {
    render(
      <ConfirmationDialog
        title="Confirm recovery"
        body={<p>Restore checkpoint ckpt_2 for run_1?</p>}
        confirmLabel="Run recovery"
        onConfirm={() => undefined}
        onCancel={() => undefined}
      />,
    )

    const dialog = screen.getByRole('dialog', { name: 'Confirm recovery' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByText('Restore checkpoint ckpt_2 for run_1?')).toBeInTheDocument()
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Cancel' }))
  })

  it('calls confirm and cancel through the explicit actions only', () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()
    render(
      <ConfirmationDialog
        title="Stop run_1"
        body={<p>A stop request will be recorded.</p>}
        confirmLabel="Request stop"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Request stop' }))
    expect(onConfirm).toHaveBeenCalledOnce()
    expect(onCancel).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('cancels on Escape, the safe action, without confirming', () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()
    render(
      <ConfirmationDialog title="Confirm reset" body="Reset?" confirmLabel="Reset" onConfirm={onConfirm} onCancel={onCancel} />,
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledOnce()
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('prevents duplicate submissions while pending', () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmationDialog
        title="Execute recovery"
        body="Validate and restore."
        confirmLabel="Execute"
        pending
        onConfirm={onConfirm}
        onCancel={() => undefined}
      />,
    )
    expect(screen.getByRole('button', { name: 'Execute' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Execute' }))
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('marks destructive operations with an explicit label, not colour alone', () => {
    render(
      <ConfirmationDialog
        title="Reset environment"
        body="Saved configuration will be replaced."
        confirmLabel="Reset"
        destructive
        onConfirm={() => undefined}
        onCancel={() => undefined}
      />,
    )
    expect(screen.getByText('This action has consequences and may not be reversible.')).toBeInTheDocument()
  })

  it('restores focus to the previously focused element on close', () => {
    const opener = document.createElement('button')
    document.body.appendChild(opener)
    opener.focus()
    expect(document.activeElement).toBe(opener)

    const { unmount } = render(
      <ConfirmationDialog title="Confirm" body="Proceed?" confirmLabel="Go" onConfirm={() => undefined} onCancel={() => undefined} />,
    )
    expect(document.activeElement).not.toBe(opener)
    unmount()
    expect(document.activeElement).toBe(opener)
    opener.remove()
  })
})
