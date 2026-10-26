/**
 * Deterministic UTC time formatting.
 *
 * Timestamps are rendered in UTC so tests and screenshots are locale-independent
 * and no local-timezone shift can be mistaken for an event ordering change.
 */

const TIME_PATTERN = /^(\d{2}):(\d{2}):(\d{2})Z$/

/** Returns `HH:MM:SSZ`, or `null` when the input is not a valid timestamp. */
export function formatUtcTime(isoTimestamp: string): string | null {
  const date = new Date(isoTimestamp)
  if (Number.isNaN(date.getTime())) return null

  const hours = String(date.getUTCHours()).padStart(2, '0')
  const minutes = String(date.getUTCMinutes()).padStart(2, '0')
  const seconds = String(date.getUTCSeconds()).padStart(2, '0')
  return `${hours}:${minutes}:${seconds}Z`
}

/** Returns `YYYY-MM-DD`, or `null` when the input is not a valid timestamp. */
export function formatUtcDate(isoTimestamp: string): string | null {
  const date = new Date(isoTimestamp)
  if (Number.isNaN(date.getTime())) return null

  const year = date.getUTCFullYear()
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const day = String(date.getUTCDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function isUtcTime(value: string): boolean {
  return TIME_PATTERN.test(value)
}
