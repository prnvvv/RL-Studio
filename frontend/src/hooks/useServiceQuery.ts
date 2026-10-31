import { useCallback, useEffect, useRef, useState } from 'react'
import type { ServiceError, ServiceResult } from '../services/types'

/**
 * State produced by a domain-service fetch.
 *
 * Error results retain the last successfully loaded data (`data`) so panels
 * can show previously known values alongside an honest failure notice instead
 * of silently emptying the view (`frontend/AGENTS.md` §11.3, §20.3). `data`
 * is null only when nothing was ever loaded successfully.
 */
export type ServiceQueryState<T> =
  | { state: 'loading' }
  | { state: 'ok'; data: T }
  | { state: 'error'; error: ServiceError; data: T | null }

export interface ServiceQuery<T> {
  state: ServiceQueryState<T>
  /** Re-run the fetcher (also invalidating any retained data). */
  reload: () => void
}

/**
 * Load a server-state value through a domain service.
 *
 * - The fetcher receives an `AbortSignal`; a new fetch cancels the previous
 *   one whenever `deps` change (stale-request discipline, §18.3).
 * - Nothing is set after unmount or after a superseded request resolves.
 * - `reload` re-runs the fetcher without remounting the component.
 *
 * The fetcher must be built from `src/services/*` domain calls; components
 * must not construct `fetch` requests inline.
 */
export function useServiceQuery<T>(
  fetcher: (signal: AbortSignal) => Promise<ServiceResult<T>>,
  deps: readonly unknown[],
): ServiceQuery<T> {
  const [query, setQuery] = useState<ServiceQueryState<T>>({ state: 'loading' })
  const [reloadNonce, setReloadNonce] = useState(0)
  // Most recent ok payload, remembered across dep changes and errors so an
  // error state can still display previously loaded data.
  const lastDataRef = useRef<T | null>(null)

  useEffect(
    () => {
      const controller = new AbortController()
      let cancelled = false

      async function run() {
        const result = await fetcher(controller.signal)
        if (cancelled) return
        if (result.state === 'ok') {
          lastDataRef.current = result.data
          setQuery(result)
        } else {
          setQuery({ ...result, data: lastDataRef.current })
        }
      }
      void run()

      return () => {
        cancelled = true
        controller.abort()
      }
    },
    // The caller supplies the real causes explicitly; the reload nonce is
    // appended so callers do not have to model it themselves.
    [...deps, reloadNonce], // eslint-disable-line react-hooks/exhaustive-deps
  )

  const reload = useCallback(() => {
    setReloadNonce((n) => n + 1)
  }, [])

  return { state: query, reload }
}
