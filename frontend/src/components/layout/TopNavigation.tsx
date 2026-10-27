import { NavLink } from 'react-router-dom'
import { ThemeToggle } from '../ThemeToggle'

const navItems = [
  { path: '/', label: 'Home' },
  { path: '/training', label: 'Training' },
  { path: '/environments', label: 'Environments' },
  { path: '/monitoring', label: 'Monitoring' },
  { path: '/reports', label: 'Reports' },
]

export function TopNavigation() {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 var(--space-6)',
        height: '56px',
        background: 'var(--bg-header)',
        borderBottom: '1px solid var(--border-primary)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-8)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <div
            style={{
              width: '24px',
              height: '24px',
              border: '2px solid var(--text-primary)',
              transform: 'rotate(45deg)',
            }}
            aria-label="Self-Healing RL Studio logo"
          />
          <span
            style={{
              fontSize: 'var(--text-md)',
              fontWeight: 600,
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            Self-Healing RL Studio
          </span>
        </div>
        <nav style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              style={({ isActive }) => ({
                padding: '6px 12px',
                textDecoration: 'none',
                fontSize: 'var(--text-base)',
                fontFamily: 'var(--font-sans)',
                color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                background: isActive ? 'var(--bg-selected)' : 'transparent',
                borderRadius: 'var(--radius-sm)',
                fontWeight: isActive ? 500 : 400,
              })}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
        <NavLink
          to="/diagnosis-recovery"
          style={({ isActive }) => ({
            padding: '6px 12px',
            textDecoration: 'none',
            fontSize: 'var(--text-base)',
            fontFamily: 'var(--font-sans)',
            color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
            background: isActive ? 'var(--bg-selected)' : 'transparent',
            borderRadius: 'var(--radius-sm)',
            fontWeight: isActive ? 500 : 400,
          })}
        >
          Diagnosis & Recovery
        </NavLink>
        <NavLink
          to="/settings"
          style={({ isActive }) => ({
            padding: '6px 12px',
            textDecoration: 'none',
            fontSize: 'var(--text-base)',
            fontFamily: 'var(--font-sans)',
            color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
            background: isActive ? 'var(--bg-selected)' : 'transparent',
            borderRadius: 'var(--radius-sm)',
            fontWeight: isActive ? 500 : 400,
          })}
        >
          Settings
        </NavLink>
        <ThemeToggle />
      </div>
    </header>
  )
}
