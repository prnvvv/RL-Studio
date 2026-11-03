import { useId, type ReactNode } from 'react'

interface Props {
  /** Accessible name of the trigger, e.g. "About Learning rate". */
  label: string
  children: ReactNode
  meta?: string
}

/**
 * A "?" help marker. The bubble opens on hover and on keyboard focus (so it is
 * reachable without a mouse) and is linked to the trigger with aria-describedby.
 */
export function InfoTip({ label, children, meta }: Props) {
  const id = useId()
  return (
    <span className="infotip">
      <button type="button" className="infotip__trigger" aria-label={label} aria-describedby={id}>
        ?
      </button>
      <span id={id} role="tooltip" className="infotip__bubble">
        {children}
        {meta && <span className="infotip__meta">{meta}</span>}
      </span>
    </span>
  )
}
