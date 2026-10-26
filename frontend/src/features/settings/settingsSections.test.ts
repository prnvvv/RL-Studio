import { describe, expect, it } from 'vitest'
import {
  defaultSectionId,
  resolveSection,
  settingsSections,
  unsupportedSections,
} from './settingsSections'

describe('settingsSections', () => {
  it('exposes only sections with supported behaviour', () => {
    expect(settingsSections.map((section) => section.id)).toEqual(['appearance'])
    expect(settingsSections[0].id).toBe(defaultSectionId)
  })

  it('documents the unsupported documented sections instead of rendering them', () => {
    const labels = unsupportedSections.map((section) => section.label)
    expect(labels).toEqual(['Profile', 'Environment', 'Training', 'Notifications', 'Integrations'])

    // Every documented gap states why it is unavailable and who owns it.
    unsupportedSections.forEach((section) => {
      expect(section.reason.length).toBeGreaterThan(20)
      expect(section.owner.length).toBeGreaterThan(0)
    })
  })

  it('resolves the default section from an empty fragment', () => {
    const result = resolveSection('')
    expect(result.kind).toBe('resolved')
    if (result.kind === 'resolved') expect(result.section.id).toBe('appearance')
  })

  it('resolves a known fragment with or without the leading hash', () => {
    expect(resolveSection('#appearance').kind).toBe('resolved')
    expect(resolveSection('appearance').kind).toBe('resolved')
  })

  it('reports an unknown fragment rather than falling back silently', () => {
    const result = resolveSection('#profile')
    expect(result).toEqual({ kind: 'unknown', requested: 'profile' })
  })

  it('treats an unsupported documented section as unknown, not navigable', () => {
    expect(resolveSection('#integrations').kind).toBe('unknown')
  })
})
