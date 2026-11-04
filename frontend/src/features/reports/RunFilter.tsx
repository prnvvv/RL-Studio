import { useId } from 'react'
import { SearchGlyph } from './ReportsIcons'

interface RunFilterProps {
  label: string
  value: string
  onChange: (value: string) => void
  onReset: () => void
  placeholder?: string
  /** Result summary announced politely after each change. */
  summary: string
  /** What the filter operates on, e.g. "the loaded page only". */
  scopeNote?: string
  /** Set when no records are loaded, so filtering cannot change anything. */
  disabled?: boolean
  /** Required with `disabled`: why the filter cannot be used. */
  disabledReason?: string
}

/**
 * Compact client-side run filter. Same behaviour and semantics as the shared `FilterBar` (a labelled search field, a
 * polite result status, a stated reason when disabled, a clear action); only the presentation differs.
 */
export function RunFilter({
  label,
  value,
  onChange,
  onReset,
  placeholder,
  summary,
  scopeNote,
  disabled = false,
  disabledReason,
}: RunFilterProps) {
  const inputId = useId()
  const noteId = useId()

  if (disabled && !disabledReason) {
    throw new Error('RunFilter requires disabledReason when disabled')
  }

  return (
    <form
      role="search"
      aria-label={`${label} controls`}
      className="rp-filter"
      onSubmit={(event) => event.preventDefault()}
    >
      <div className="rp-filter__row">
        <div className="rp-filter__field">
          <label htmlFor={inputId} className="rp-filter__label">
            {label}
          </label>
          <div className="rp-filter__control">
            <SearchGlyph />
            <input
              id={inputId}
              type="search"
              className="rp-filter__input"
              value={value}
              disabled={disabled}
              placeholder={placeholder}
              aria-describedby={noteId}
              onChange={(event) => onChange(event.target.value)}
            />
          </div>
        </div>
        {value !== '' && !disabled ? (
          <button type="button" className="mon-button" onClick={onReset}>
            Clear filter
          </button>
        ) : null}
      </div>
      <p
        id={noteId}
        role="status"
        aria-label="Filter results"
        aria-live="polite"
        className="rp-filter__note"
      >
        {disabled ? disabledReason : summary}
        {!disabled && scopeNote ? ` ${scopeNote}` : null}
      </p>
    </form>
  )
}
