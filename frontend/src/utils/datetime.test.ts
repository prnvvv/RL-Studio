import { describe, expect, it } from 'vitest'
import { formatUtcDate, formatUtcTime, isUtcTime } from './datetime'

describe('formatUtcTime', () => {
  it('formats a UTC instant as HH:MM:SSZ', () => {
    expect(formatUtcTime('2026-10-25T12:04:09Z')).toBe('12:04:09Z')
    expect(formatUtcTime('2026-10-25T00:00:00Z')).toBe('00:00:00Z')
  })

  it('normalises an offset timestamp to UTC', () => {
    expect(formatUtcTime('2026-10-25T14:04:09+02:00')).toBe('12:04:09Z')
  })

  it('returns null for an invalid timestamp instead of inventing a time', () => {
    expect(formatUtcTime('not-a-timestamp')).toBeNull()
  })
})

describe('formatUtcDate', () => {
  it('formats the UTC calendar date', () => {
    expect(formatUtcDate('2026-10-25T23:59:59Z')).toBe('2026-10-25')
    expect(formatUtcDate('2026-01-02T00:00:00Z')).toBe('2026-01-02')
  })

  it('returns null for an invalid timestamp', () => {
    expect(formatUtcDate('')).toBeNull()
  })
})

describe('isUtcTime', () => {
  it('accepts the format produced by formatUtcTime only', () => {
    expect(isUtcTime('12:04:09Z')).toBe(true)
    expect(isUtcTime('12:04:09')).toBe(false)
    expect(isUtcTime('2026-10-25T12:04:09Z')).toBe(false)
  })
})
