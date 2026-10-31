import { ReactNode, useId } from 'react'

interface FormFieldProps {
  /** Visible label text; always rendered (frontend/AGENTS.md §15.1). */
  label: string
  /** Optional guidance below the label. */
  hint?: string
  /**
   * Validation message. Rendered inside a live region and associated with the
   * control so screen readers announce it. Passing this marks the control
   * invalid; colour or border style alone never signals the problem.
   */
  error?: string
  children: (associatedProps: {
    id: string
    'aria-describedby': string | undefined
    'aria-invalid': boolean | undefined
  }) => ReactNode
}

/**
 * Label/description/validation wrapper that wires up the accessibility
 * associations for the control rendered by its child function.
 *
 * The child-function form keeps the association explicit and typed: a control
 * must spread the provided props onto the actual input element, so miswiring
 * is impossible to do accidentally.
 */
export function FormField({ label, hint, error, children }: FormFieldProps) {
  const controlId = useId()
  const hintId = useId()
  const errorId = useId()

  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ')
  const describedProps = {
    id: controlId,
    'aria-describedby': describedBy || undefined,
    'aria-invalid': error ? true : undefined,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
      <label
        htmlFor={controlId}
        style={{
          fontSize: 'var(--text-sm)',
          color: 'var(--text-primary)',
          fontWeight: 600,
          fontFamily: 'var(--font-sans)',
        }}
      >
        {label}
      </label>
      {hint && (
        <span id={hintId} style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          {hint}
        </span>
      )}
      {children(describedProps)}
      {error && (
        <span
          id={errorId}
          role="alert"
          style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontWeight: 600 }}
        >
          {error}
        </span>
      )}
    </div>
  )
}
