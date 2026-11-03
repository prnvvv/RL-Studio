/**
 * Minimal toast notifications for the studio (bottom-right, monochrome).
 *
 * Toasts report the outcome of user actions and connection changes. Errors are
 * announced assertively and stay longer; everything auto-dismisses and can be
 * dismissed by hand.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

export type ToastTone = 'success' | 'info' | 'warning' | 'error'

export interface ToastItem {
  id: number
  tone: ToastTone
  message: string
}

export interface ToastApi {
  push: (tone: ToastTone, message: string) => void
  dismiss: (id: number) => void
}

export const MAX_TOASTS = 4
const TTL_MS: Record<ToastTone, number> = { success: 3500, info: 4000, warning: 6000, error: 8000 }

/** Pure list update, exported for tests: newest last, bounded, identical consecutive messages collapsed. */
export function addToast(items: ToastItem[], next: ToastItem): ToastItem[] {
  const last = items[items.length - 1]
  const base = last && last.tone === next.tone && last.message === next.message ? items.slice(0, -1) : items
  const merged = [...base, next]
  return merged.length > MAX_TOASTS ? merged.slice(merged.length - MAX_TOASTS) : merged
}

const NOOP: ToastApi = { push: () => undefined, dismiss: () => undefined }
const ToastContext = createContext<ToastApi>(NOOP)

export function useToast(): ToastApi {
  return useContext(ToastContext)
}

function Toast({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(item.id), TTL_MS[item.tone])
    return () => window.clearTimeout(timer)
  }, [item, onDismiss])
  return (
    <div className="toast" data-tone={item.tone} role={item.tone === 'error' ? 'alert' : 'status'}>
      <span className="toast__message">{item.message}</span>
      <button type="button" className="toast__close" aria-label="Dismiss notification" onClick={() => onDismiss(item.id)}>
        ×
      </button>
    </div>
  )
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const counter = useRef(0)

  const dismiss = useCallback((id: number) => setItems((current) => current.filter((t) => t.id !== id)), [])
  const push = useCallback((tone: ToastTone, message: string) => {
    counter.current += 1
    setItems((current) => addToast(current, { id: counter.current, tone, message }))
  }, [])
  const api = useMemo(() => ({ push, dismiss }), [push, dismiss])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" role="region" aria-label="Notifications">
        {items.map((item) => (
          <Toast key={item.id} item={item} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}
