import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  MOCK_DATA_LABEL,
  assertMocksEnabled,
  labeledMockData,
  labeledMockResult,
  mocksEnabled,
} from './index'

describe('mocksEnabled', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('is enabled only when VITE_USE_MOCKS is exactly "true"', () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    expect(mocksEnabled()).toBe(true)

    vi.stubEnv('VITE_USE_MOCKS', 'false')
    expect(mocksEnabled()).toBe(false)

    vi.stubEnv('VITE_USE_MOCKS', '1')
    expect(mocksEnabled()).toBe(false)

    vi.stubEnv('VITE_USE_MOCKS', '')
    expect(mocksEnabled()).toBe(false)
  })
})

describe('labeling', () => {
  it('carries the fixed sample-data label with every fixture', () => {
    const labeled = labeledMockData({ run_id: 'run_mock_1' })
    expect(labeled.label).toBe(MOCK_DATA_LABEL)
    expect(labeled.label).toBe('Sample data')
    expect(labeled.data).toEqual({ run_id: 'run_mock_1' })
  })

  it('wraps fixtures in the shared service-result contract', () => {
    const result = labeledMockResult({ total_steps: 48 })
    expect(result.state).toBe('ok')
    if (result.state === 'ok') {
      expect(result.data.label).toBe('Sample data')
      expect(result.data.data).toEqual({ total_steps: 48 })
    }
  })
})

describe('assertMocksEnabled', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('passes when mocks are explicitly enabled', () => {
    vi.stubEnv('VITE_USE_MOCKS', 'true')
    expect(() => assertMocksEnabled('intent-analysis')).not.toThrow()
  })

  it('fails closed with a named error when mocks are disabled', () => {
    vi.stubEnv('VITE_USE_MOCKS', 'false')
    expect(() => assertMocksEnabled('intent-analysis')).toThrow(/intent-analysis/)
    expect(() => assertMocksEnabled('intent-analysis')).toThrow(/VITE_USE_MOCKS/)
  })
})
