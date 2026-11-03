import { useState } from 'react'
import { RANGES, type RangeKey } from './metricData'

/** Which slice of history a chart shows; each chart keeps its own choice. */
export function useRange(initial: RangeKey = 'all') {
  const [range, setRange] = useState<RangeKey>(initial)
  const control = (
    <div className="range" role="group" aria-label="Time range">
      {RANGES.map((option) => (
        <button
          key={option.key}
          type="button"
          aria-pressed={range === option.key}
          onClick={() => setRange(option.key)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
  return { range, control }
}
