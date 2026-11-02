/**
 * Development mock adapter scaffolding (frontend/AGENTS.md §16).
 *
 * Rules this module enforces for every future mock-backed service:
 *
 * 1. Mocks are opt-in through `VITE_USE_MOCKS=true` only — never a silent
 *    fallback when a real API request fails (`assertMocksEnabled`).
 * 2. Every fixture is wrapped by `labeledMockData`, forcing the presentation
 *    layer to attach `MOCK_DATA_LABEL` so fixture-backed views are visibly
 *    marked as sample data, never as live system behaviour.
 * 3. Mock adapters live in `src/mocks/`, separate from the production
 *    adapters in `src/services/`, and return the same `ServiceResult`
 *    contract so the swap is mechanical.
 */
import type { ServiceResult } from '../services/types'

/** Visible label that must accompany every fixture-backed view. */
export const MOCK_DATA_LABEL = 'Sample data'

/** Read the opt-in flag once; `true` enables mock-backed adapters. */
export function mocksEnabled(): boolean {
  return import.meta.env.VITE_USE_MOCKS === 'true'
}

/** Fail-closed guard: mock-backed capability used while mocks are disabled. */
export function assertMocksEnabled(capability: string): void {
  if (!mocksEnabled()) {
    throw new Error(
      `Mock adapter for "${capability}" requires VITE_USE_MOCKS=true. Enable mocks intentionally to build the interface.`,
    )
  }
}

export interface MockData<T> {
  data: T
  label: typeof MOCK_DATA_LABEL
}

/**
 * Wrap a fixture so its visible label travels with the data. Presentation
 * components are expected to render `label` next to fixture-backed values —
 * dropping it should be as visible a mistake as inventing a metric.
 */
export function labeledMockData<T>(data: T): MockData<T> {
  return { data, label: MOCK_DATA_LABEL }
}

/** Wrap a fixture as an ok service result carrying its shared label. */
export function labeledMockResult<T>(data: T): ServiceResult<MockData<T>> {
  return { state: 'ok', data: labeledMockData(data) }
}

/**
 * Remove the shared `Sample data` wrapper from a service payload.
 *
 * Presentation helpers and a service payload may both carry the contract
 * `MockData<T>` shape; this returns the underlying value either way.
 */
export function unwrapMockData<T extends object>(payload: T | MockData<T>): T {
  return 'label' in payload ? (payload as MockData<T>).data : payload
}
