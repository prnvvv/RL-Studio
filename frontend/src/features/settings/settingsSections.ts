/**
 * Settings sections.
 *
 * Only sections with meaningful, supported behaviour are navigable
 * (`frontend/AGENTS.md` §8.7, TODO T-1502). Profile needs authentication and
 * profile data, and Environment/Training/Notifications/Integrations need
 * backend persistence or provider capability, so none of them are offered as
 * navigation entries — an empty or decorative section is prohibited.
 *
 * They are still described, in text, by `unsupportedSections`, so a developer
 * can see why the documented sections are absent without a dead control.
 */

export type SettingsSectionId = 'appearance'

export interface SettingsSection {
  id: SettingsSectionId
  label: string
  /** One-line description shown under the panel heading. */
  description: string
}

export const settingsSections: SettingsSection[] = [
  {
    id: 'appearance',
    label: 'Appearance',
    description: 'Theme for the whole application.',
  },
]

export const defaultSectionId: SettingsSectionId = 'appearance'

export interface UnsupportedSection {
  label: string
  reason: string
  owner: string
}

export const unsupportedSections: UnsupportedSection[] = [
  {
    label: 'Profile',
    reason:
      'Requires authentication and profile data. Neither is implemented, so no account details are shown.',
    owner: 'Person 1 — frontend, once an auth contract is agreed',
  },
  {
    label: 'Environment',
    reason: 'Requires a saved, backend-owned environment default. No settings endpoint exists.',
    owner: 'Person 2 — RL engine',
  },
  {
    label: 'Training',
    reason:
      'Requires backend-owned run defaults. Values would otherwise be invented in the browser.',
    owner: 'Person 2 — RL engine',
  },
  {
    label: 'Notifications',
    reason: 'Requires a notification service and delivery preferences. No transport is configured.',
    owner: 'Shared — not yet scoped',
  },
  {
    label: 'Integrations',
    reason:
      'Provider configuration (including the Meta AI provider) is backend-owned and is not exposed to the browser.',
    owner: 'Person 3 — diagnosis provider configuration',
  },
]

export type SectionResolution =
  { kind: 'resolved'; section: SettingsSection } | { kind: 'unknown'; requested: string }

/**
 * Resolves a URL fragment to a section. An unknown fragment is reported rather
 * than silently redirected, so a stale link cannot look like it worked.
 */
export function resolveSection(fragment: string): SectionResolution {
  const requested = fragment.replace(/^#/, '')
  if (requested === '') {
    return { kind: 'resolved', section: settingsSections[0] }
  }

  const match = settingsSections.find((section) => section.id === requested)
  if (match) return { kind: 'resolved', section: match }

  return { kind: 'unknown', requested }
}
