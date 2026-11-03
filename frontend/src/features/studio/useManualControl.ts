import { useEffect } from 'react'
import { actionForKey } from './humanControl'

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
}

/**
 * While manual control is active, arrow keys and WASD send actions for the
 * current environment. `send` reports whether the message left the browser.
 */
export function useManualControl(
  active: boolean,
  renderer: string | null,
  send: (action: number) => void,
): void {
  useEffect(() => {
    if (!active) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || isEditable(event.target)) return
      const action = actionForKey(renderer, event.key)
      if (action === null) return
      // Arrow keys would otherwise scroll the page or move focus.
      event.preventDefault()
      send(action)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [active, renderer, send])
}
