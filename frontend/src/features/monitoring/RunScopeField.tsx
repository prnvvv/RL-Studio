import { useState } from 'react'
import { FormField } from '../../components/ui/FormField'

export interface RunScopeFieldProps {
  /** Committed run identifier, or '' when the page is not scoped to a run. */
  value: string
  /** Commit a non-empty, trimmed run identifier. */
  onSubmit: (runId: string) => void
  /** Form id so a page header action can submit/focus this control. */
  formId?: string
  /** Set while a consequential operation is in flight and scope must not change. */
  disabled?: boolean
  label?: string
  hint?: string
  submitLabel?: string
}

/**
 * Run-identifier input that scopes Training/Monitoring to one recorded run.
 *
 * The page URL (not component state) is the scope of record, so committing the
 * field navigates rather than storing a private selection that a refresh or a
 * shared link would lose.
 *
 * Validation is deliberately minimal: the identifier is compared verbatim with
 * what the backend reports, so the field is never normalised beyond trimming,
 * and an empty value is rejected instead of silently clearing the scope.
 */
export function RunScopeField({
  value,
  onSubmit,
  formId,
  disabled = false,
  label = 'Run identifier',
  hint = 'Scopes this page to one recorded run. Use the identifier the run was started with.',
  submitLabel = 'Use run',
}: RunScopeFieldProps) {
  const [draft, setDraft] = useState(value)
  const [committedValue, setCommittedValue] = useState(value)
  const [error, setError] = useState<string | null>(null)

  // Adopt an externally changed scope (link navigation, back/forward) without
  // an effect, and discard any uncommitted edit for the previous run.
  if (committedValue !== value) {
    setCommittedValue(value)
    setDraft(value)
    setError(null)
  }

  return (
    <form
      id={formId}
      onSubmit={(event) => {
        event.preventDefault()
        const trimmed = draft.trim()
        if (trimmed === '') {
          setError('Enter a run identifier.')
          return
        }
        setError(null)
        onSubmit(trimmed)
      }}
      style={{ display: 'flex', alignItems: 'flex-end', gap: 'var(--space-2)', flexWrap: 'wrap' }}
    >
      <div style={{ flex: '1 1 220px', minWidth: 0 }}>
        <FormField label={label} hint={hint} error={error ?? undefined}>
          {(associatedProps) => (
            <input
              type="text"
              className="text-input"
              value={draft}
              disabled={disabled}
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => setDraft(event.target.value)}
              {...associatedProps}
            />
          )}
        </FormField>
      </div>
      <button
        type="submit"
        disabled={disabled}
        style={{
          padding: '6px 14px',
          background: 'transparent',
          border: '1px solid var(--border-primary)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--text-primary)',
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.6 : 1,
          fontFamily: 'var(--font-sans)',
        }}
      >
        {submitLabel}
      </button>
    </form>
  )
}
