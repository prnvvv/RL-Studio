import { useId } from 'react'

interface FilterBarProps {
  /** Visible label for the search field. */
  label: string
  value: string
  onChange: (value: string) => void
  onReset: () => void
  placeholder?: string
  /** Result summary announced politely after each change. */
  summary: string
  /** Explains what the filter operates on, e.g. "applies to the loaded page only". */
  scopeNote?: string
  /** Set when no records are loaded, so filtering cannot change anything. */
  disabled?: boolean
  /** Required with `disabled`: why the filter cannot be used. */
  disabledReason?: string
}

/**
 * Client-side filter control.
 *
 * The filter is debounce-free on purpose: it operates on an already-loaded
 * bounded page and issues no request, so delaying the result would only add
 * latency. When the caller has no records, the control is disabled with a
 * stated reason instead of appearing to filter nothing.
 */
export function FilterBar({
  label,
  value,
  onChange,
  onReset,
  placeholder,
  summary,
  scopeNote,
  disabled = false,
  disabledReason,
}: FilterBarProps) {
  const inputId = useId()
  const noteId = useId()

  if (disabled && !disabledReason) {
    throw new Error('FilterBar requires disabledReason when disabled')
  }

  return (
    <form
      role="search"
      aria-label={`${label} controls`}
      onSubmit={(event) => event.preventDefault()}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <div
        style={{ display: 'flex', alignItems: 'flex-end', gap: 'var(--space-3)', flexWrap: 'wrap' }}
      >
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
            minWidth: 0,
            flex: '1 1 280px',
          }}
        >
          <label
            htmlFor={inputId}
            style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}
          >
            {label}
          </label>
          <input
            id={inputId}
            type="search"
            value={value}
            disabled={disabled}
            placeholder={placeholder}
            aria-describedby={noteId}
            onChange={(event) => onChange(event.target.value)}
            style={{
              padding: 'var(--space-2) var(--space-3)',
              background: 'var(--bg-input)',
              color: disabled ? 'var(--text-muted)' : 'var(--text-primary)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-sm)',
              fontSize: 'var(--text-sm)',
              fontFamily: 'var(--font-sans)',
              cursor: disabled ? 'not-allowed' : 'text',
            }}
          />
        </div>

        {value !== '' && !disabled ? (
          <button
            type="button"
            onClick={onReset}
            style={{
              padding: 'var(--space-2) var(--space-3)',
              background: 'transparent',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-sm)',
              fontSize: 'var(--text-xs)',
              fontFamily: 'var(--font-sans)',
              cursor: 'pointer',
            }}
          >
            Clear filter
          </button>
        ) : null}
      </div>

      <p
        id={noteId}
        role="status"
        aria-label="Filter results"
        aria-live="polite"
        style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}
      >
        {disabled ? disabledReason : summary}
        {!disabled && scopeNote ? ` ${scopeNote}` : null}
      </p>
    </form>
  )
}
