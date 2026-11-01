/**
 * Display formatting for raw expected/observed values from verification
 * checks. Shared by the verdict card and test suites; deliberately separate
 * from the component file so the component module only exports components.
 */
export function formatCheckValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (typeof value === 'symbol' || typeof value === 'function') return '—'
  try {
    return JSON.stringify(value) ?? '—'
  } catch {
    return '—'
  }
}
