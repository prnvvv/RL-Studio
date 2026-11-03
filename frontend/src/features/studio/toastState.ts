import { createContext, useContext } from 'react'

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
export const TTL_MS: Record<ToastTone, number> = {
  success: 3500,
  info: 4000,
  warning: 6000,
  error: 8000,
}

/** Pure list update, exported for tests: newest last, bounded, identical consecutive messages collapsed. */
export function addToast(items: ToastItem[], next: ToastItem): ToastItem[] {
  const last = items[items.length - 1]
  const base =
    last && last.tone === next.tone && last.message === next.message ? items.slice(0, -1) : items
  const merged = [...base, next]
  return merged.length > MAX_TOASTS ? merged.slice(merged.length - MAX_TOASTS) : merged
}

const NOOP: ToastApi = { push: () => undefined, dismiss: () => undefined }
export const ToastContext = createContext<ToastApi>(NOOP)

export function useToast(): ToastApi {
  return useContext(ToastContext)
}
