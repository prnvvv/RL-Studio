import { ChangeEvent, TextareaHTMLAttributes } from 'react'

interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  value: string
  onChange: (event: ChangeEvent<HTMLTextAreaElement>) => void
  /** Standalone invalid marker; `FormField` also sets aria-invalid itself. */
  invalid?: boolean
}

/**
 * Monochrome multiline text input on the documented control styles
 * (`styles/controls.css`). Value and change handling stay fully controlled so
 * parent forms keep values across recoverable failures (§15.1).
 */
export function TextArea({ invalid, rows = 4, ...rest }: TextAreaProps) {
  return <textarea className="text-area" rows={rows} aria-invalid={invalid || undefined} {...rest} />
}
