import { Link, useLocation } from 'react-router-dom'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import { Panel } from '../components/ui/Panel'
import { AppearanceSection } from '../features/settings/AppearanceSection'
import {
  resolveSection,
  settingsSections,
  unsupportedSections,
} from '../features/settings/settingsSections'

export function SettingsPage() {
  const location = useLocation()
  const resolution = resolveSection(location.hash)

  return (
    <ApplicationShell>
      <div className="page-stack">
        <div className="page-header">
          <div>
            <h1
              style={{
                fontSize: 'var(--text-2xl)',
                fontWeight: 600,
                margin: 0,
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Settings
            </h1>
            <p
              style={{
                fontSize: 'var(--text-base)',
                color: 'var(--text-secondary)',
                margin: '4px 0 0 0',
                fontFamily: 'var(--font-sans)',
                maxWidth: '78ch',
              }}
            >
              Application preferences. Only settings with a real, supported effect are listed.
            </p>
          </div>
        </div>

        <div className="settings-layout">
          <nav aria-label="Settings sections" className="settings-nav">
            {settingsSections.map((section) => {
              const isActive =
                resolution.kind === 'resolved' && resolution.section.id === section.id

              return (
                <Link
                  key={section.id}
                  to={{ hash: `#${section.id}` }}
                  className="settings-nav-link"
                  aria-current={isActive ? 'page' : undefined}
                >
                  {section.label}
                </Link>
              )
            })}
          </nav>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            {resolution.kind === 'unknown' ? (
              <Panel title="Unknown section">
                <p
                  style={{
                    margin: 0,
                    fontSize: 'var(--text-sm)',
                    color: 'var(--text-secondary)',
                    fontFamily: 'var(--font-sans)',
                  }}
                >
                  No settings section named &ldquo;{resolution.requested}&rdquo; exists, so nothing
                  was selected. <Link to={{ hash: '#appearance' }}>Go to Appearance</Link>.
                </p>
              </Panel>
            ) : (
              <Panel title={resolution.section.label} description={resolution.section.description}>
                <AppearanceSection />
              </Panel>
            )}

            <Panel
              title="Not available yet"
              description="Documented sections with no supported behaviour are not shown in the navigation."
            >
              <dl style={{ margin: 0, display: 'flex', flexDirection: 'column' }}>
                {unsupportedSections.map((section, index) => (
                  <div
                    key={section.label}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '2px',
                      padding: 'var(--space-2) 0',
                      borderTop: index === 0 ? 'none' : '1px solid var(--border-secondary)',
                    }}
                  >
                    <dt
                      style={{
                        fontSize: 'var(--text-sm)',
                        color: 'var(--text-primary)',
                        fontFamily: 'var(--font-sans)',
                      }}
                    >
                      {section.label}
                    </dt>
                    <dd
                      style={{
                        margin: 0,
                        fontSize: 'var(--text-xs)',
                        color: 'var(--text-secondary)',
                        fontFamily: 'var(--font-sans)',
                        lineHeight: 1.6,
                        maxWidth: '82ch',
                      }}
                    >
                      {section.reason}
                      <span style={{ color: 'var(--text-muted)' }}> Owner: {section.owner}.</span>
                    </dd>
                  </div>
                ))}
              </dl>
            </Panel>
          </div>
        </div>
      </div>
    </ApplicationShell>
  )
}
