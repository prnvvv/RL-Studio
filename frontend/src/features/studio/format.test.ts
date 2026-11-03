import { describe, expect, it } from 'vitest'
import { downsample, formatDuration, formatNumber, formatPercent } from './format'

describe('format helpers', () => {
  it('renders missing values as an em dash, never as zero', () => {
    expect(formatNumber(null)).toBe('—')
    expect(formatNumber(Number.NaN)).toBe('—')
    expect(formatPercent(undefined)).toBe('—')
    expect(formatPercent(0)).toBe('0%')
  })

  it('formats durations', () => {
    expect(formatDuration(65)).toBe('1:05')
    expect(formatDuration(3725)).toBe('1:02:05')
  })

  it('downsamples while keeping the final point', () => {
    const items = Array.from({ length: 1000 }, (_, i) => i)
    const out = downsample(items, 100)
    expect(out).toHaveLength(100)
    expect(out[out.length - 1]).toBe(999)
    expect(downsample([1, 2], 100)).toEqual([1, 2])
  })
})
