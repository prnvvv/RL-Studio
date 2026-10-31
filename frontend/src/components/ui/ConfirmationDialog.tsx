import { ReactNode, useEffect, useRef } from 'react'

interface ConfirmationDialogProps {
  title: string
  /** What the requested operation is, in user-facing, non-sensitive terms. */
  body: ReactNode
  confirmLabel: string
  cancelLabel?: string
  /**
   * Marks the confirm action destructive or consequential (stop run, reset
   * environment, execute recovery). Rendered with explicit styling, not
   * colour only (frontend/AGENTS.md §15.2).
   */
  destructive?: boolean
  /** Set while the confirmed operation request is in flight. */
  pending?: boolean
  onConfirm: () => void
  onCancel: () => void
}

/**
 * Accessible modal confirmation for consequential operations.
 *
 * - `role="dialog"` with `aria-modal` and a labelled title.
 * - Focus moves to the cancel button on open (the safe action) and is
 *   restored to the previously focused element on close.
 * - Escape cancels; nothing is confirmed without an explicit button press.
 * - The dialog never reports the operation as done — the caller owns the
 *   resulting state; `pending` only prevents duplicate submissions (§15.2).
 */
export function ConfirmationDialog({
  title,
  body,
  confirmLabel,
  cancelLabel = 'Cancel',
  destructive = false,
  pending = false,
  onConfirm,
  onCancel,
}: ConfirmationDialogProps) {
  const cancelButtonRef = useRef<HTMLButtonElement>(null)
  const previouslyFocused = useRef<HTMLElement | null>(null)

  useEffect(() => {
    previouslyFocused.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    cancelButtonRef.current?.focus()
    return () => {
      previouslyFocused.current?.focus()
    }
  }, [])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCancel()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [onCancel])

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg-primary)',
        fontFamily: 'var(--font-sans)',
        zIndex: 50,
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirmation-dialog-title"
        style={{
          background: 'var(--bg-panel)',
          border: '1px solid var(--border-primary)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-5)',
          width: 'min(420px, calc(100vw - var(--space-8)))',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-3)',
        }}
      >
        <h2
          id="confirmation-dialog-title"
          style={{
            margin: 0,
            fontSize: 'var(--text-md)',
            color: 'var(--text-primary)',
          }}
        >
          {title}
        </h2>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>{body}</div>
        {destructive && (
          <span
            style={{
              fontSize: 'var(--text-xs)',
              color: 'var(--text-secondary)',
              fontWeight: 600,
            }}
          >
            This action has consequences and may not be reversible.
          </span>
        )}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 'var(--space-2)',
            marginTop: 'var(--space-2)',
          }}
        >
          <button
            type="button"
            ref={cancelButtonRef}
            onClick={onCancel}
            disabled={pending}
            style={{
              padding: '6px 14px',
              background: 'var(--bg-input)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-primary)',
              cursor: pending ? 'not-allowed' : 'pointer',
            }}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            aria-busy={pending || undefined}
            style={{
              padding: '6px 14px',
              background: 'var(--bg-panel-raised)',
              border: `1px ${destructive ? 'dashed' : 'solid'} var(--border-primary)`,
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-primary)',
              fontWeight: 600,
              cursor: pending ? 'not-allowed' : 'pointer',
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
