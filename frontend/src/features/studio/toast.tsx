/**
 * Minimal toast notifications for the studio (bottom-right, monochrome).
 *
 * Toasts report the outcome of user actions and connection changes. Errors are
 * announced assertively and stay longer; everything auto-dismisses and can be
 * dismissed by hand.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { addToast, ToastContext, TTL_MS, type ToastItem, type ToastTone } from './toastState'

function Toast({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(item.id), TTL_MS[item.tone])
    return () => window.clearTimeout(timer)
  }, [item, onDismiss])
  return (
    <div className="toast" data-tone={item.tone} role={item.tone === 'error' ? 'alert' : 'status'}>
      <span className="toast__message">{item.message}</span>
      <button
        type="button"
        className="toast__close"
        aria-label="Dismiss notification"
        onClick={() => onDismiss(item.id)}
      >
        ×
      </button>
    </div>
  )
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const counter = useRef(0)

  const dismiss = useCallback(
    (id: number) => setItems((current) => current.filter((t) => t.id !== id)),
    [],
  )
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
