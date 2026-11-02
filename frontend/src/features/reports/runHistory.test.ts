import { describe, expect, it } from 'vitest'
import { filterRuns, runDetailPath, RunSummary } from './runHistory'

const runs: RunSummary[] = [
  {
    id: 'run_0001',
    environment: 'warehouse_v1',
    steps: '12000',
    successRate: '84.0',
    status: 'Recovered',
    date: '2026-10-24',
  },
  {
    id: 'run_0002',
    environment: 'warehouse_v1',
    steps: '12000',
    successRate: null,
    status: 'Failed',
    date: '2026-10-24',
  },
  {
    id: 'run_0003',
    environment: 'cartpole_v1',
    steps: null,
    successRate: null,
    status: null,
    date: null,
  },
]

describe('filterRuns', () => {
  it('returns every run for an empty or whitespace-only query', () => {
    expect(filterRuns(runs, '')).toHaveLength(3)
    expect(filterRuns(runs, '   ')).toHaveLength(3)
  })

  it('matches identifiers case-insensitively', () => {
    expect(filterRuns(runs, 'RUN_0002').map((run) => run.id)).toEqual(['run_0002'])
  })

  it('matches environment and status text', () => {
    expect(filterRuns(runs, 'warehouse').map((run) => run.id)).toEqual(['run_0001', 'run_0002'])
    expect(filterRuns(runs, 'recovered').map((run) => run.id)).toEqual(['run_0001'])
  })

  it('preserves the supplied order and does not re-sort', () => {
    expect(filterRuns(runs, 'run_').map((run) => run.id)).toEqual([
      'run_0001',
      'run_0002',
      'run_0003',
    ])
  })

  it('returns an empty list when nothing matches, so callers can distinguish filtered-empty', () => {
    expect(filterRuns(runs, 'no-such-run')).toEqual([])
  })

  it('never matches on a placeholder for a missing value', () => {
    // run_0003 has null steps/successRate/status/date. If those were coerced to
    // "null"/"undefined"/"0" text, a query for those words would match it.
    expect(filterRuns(runs, 'null')).toEqual([])
    expect(filterRuns(runs, 'undefined')).toEqual([])
    expect(filterRuns(runs, 'not available')).toEqual([])
  })
})

describe('runDetailPath', () => {
  it('builds the unified diagnostic report route for a run id', () => {
    expect(runDetailPath('run_0001')).toBe('/reports/run_0001')
  })

  it('encodes characters a run id could contain but a URL path segment cannot', () => {
    expect(runDetailPath('run/weird id?')).toBe('/reports/run%2Fweird%20id%3F')
  })
})
