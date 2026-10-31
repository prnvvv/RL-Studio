import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useServiceQuery } from './useServiceQuery'
import type { ServiceResult } from '../services/types'

const okResult = <T,>(data: T) => ({ state: 'ok' as const, data })
const errorResult = (
  kind: 'not_found' | 'unavailable' | 'cancelled' = 'not_found',
  message = 'The requested record was not found.',
) =>
  ({ state: 'error' as const, error: { kind, message } })

/** Resolve the promise at `index` if it exists; keeps act-wrapped resolution terse. */
function resolveAt(
  resolvers: Array<(r: ServiceResult<string>) => void>,
  index: number,
  value: ServiceResult<string>,
) {
  resolvers[index]?.(value)
}

describe('useServiceQuery', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('starts loading and resolves to loaded data', async () => {
    let resolve: (r: ServiceResult<string>) => void = () => {}
    const fetcher = vi.fn(
      (_signal: AbortSignal) => new Promise<ServiceResult<string>>((res) => (resolve = res)),
    )
    const { result } = renderHook(() => useServiceQuery(fetcher, []))
    expect(result.current.state).toEqual({ state: 'loading' })
    await waitFor(() => expect(fetcher).toHaveBeenCalledOnce())
    act(() => { resolve?.(okResult('data-v1') as ServiceResult<string>) })
    await waitFor(() => expect(result.current.state).toEqual({ state: 'ok', data: 'data-v1' }))
  })

  it('retains previously loaded data when a reload fails', async () => {
    // One deferred per fetch so both resolutions are explicitly act-wrapped.
    const resolvers: Array<(r: ServiceResult<string>) => void> = []
    const fetcher = vi.fn(
      (_signal: AbortSignal) =>
        new Promise<ServiceResult<string>>((res) => {
          resolvers.push(res as (r: ServiceResult<string>) => void)
        }),
    )
    const { result, rerender } = renderHook(() => useServiceQuery(fetcher, []))
    act(() => resolveAt(resolvers, 0, okResult('first')))
    await waitFor(() => expect(result.current.state).toEqual({ state: 'ok', data: 'first' }))

    act(() => {
      result.current.reload()
    })
    rerender()
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))
    act(() => resolveAt(resolvers, 1, errorResult('unavailable') as unknown as ServiceResult<string>))
    await waitFor(() => expect(result.current.state.state).toBe('error'))
    const errorState = result.current.state as { state: 'error'; data: string | null }
    expect(errorState.data).toBe('first')
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('discards superseded results when dependencies change mid-flight', async () => {
    const resolvers: Array<(r: ServiceResult<string>) => void> = []
    const fetcher = vi.fn(
      (_signal: AbortSignal) =>
        new Promise<ServiceResult<string>>((res) => {
          resolvers.push(res as (r: ServiceResult<string>) => void)
        }),
    )
    const { rerender, result } = renderHook(({ dep }: { dep: string }) => useServiceQuery(fetcher, [dep]), {
      initialProps: { dep: 'a' },
    })
    rerender({ dep: 'b' })
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))

    act(() => { resolvers[1]?.(okResult('new') as ServiceResult<string>) })
    await waitFor(() => expect(result.current.state).toEqual({ state: 'ok', data: 'new' }))

    act(() => { resolvers[0]?.(okResult('outdated') as ServiceResult<string>) })
    expect(result.current.state).toEqual({ state: 'ok', data: 'new' })
  })

  it('cancels and freezes state on unmount', async () => {
    const resolvers: Array<(r: ServiceResult<string>) => void> = []
    const fetcher = vi.fn(
      (_signal: AbortSignal) =>
        new Promise<ServiceResult<string>>((res) => {
          resolvers.push(res as (r: ServiceResult<string>) => void)
        }),
    )
    const { unmount, result } = renderHook(() => useServiceQuery(fetcher, []))
    unmount()
    act(() => { resolvers[0]?.(okResult('after-unmount') as ServiceResult<string>) })
    expect(result.current.state).toEqual({ state: 'loading' })
  })

  it('reports an aborted request as an error result, not loading or success', async () => {
    const fetcher = vi.fn((signal: AbortSignal) => {
      return new Promise<ReturnType<typeof errorResult>>((resolve) => {
        signal.addEventListener('abort', () => resolve(errorResult('cancelled') as never))
      })
    })
    const { unmount, result } = renderHook(() => useServiceQuery(fetcher, []))
    unmount()
    expect(fetcher).toHaveBeenCalledTimes(1)
    await Promise.resolve()
    expect(result.current.state).toEqual({ state: 'loading' })
  })
})


