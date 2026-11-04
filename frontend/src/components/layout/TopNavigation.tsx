import { useEffect, useId, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { ThemeToggle } from '../ThemeToggle'
import { LogoMark } from '../../features/landing/icons'
import { ActiveProjectChip } from '../../features/projects/ActiveProjectChip'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { useUser, SignOutButton } from '@clerk/react'

/** Matches the stacking breakpoint already used for page layouts (`src/styles/layout.css`). */
const NARROW_QUERY = '(max-width: 960px)'

interface NavItem {
  to: string
  label: string
}

/** Studio is the single workspace entry: it owns the agent/environment library and training. */
const STUDIO_PATH = '/studio'

const primaryNavItems: NavItem[] = [
  { to: '/projects', label: 'Projects' },
  { to: STUDIO_PATH, label: 'Studio' },
  { to: '/monitoring', label: 'Monitoring' },
  { to: '/reports', label: 'Reports' },
  { to: '/diagnosis-recovery', label: 'Diagnosis & Recovery' },
]

const secondaryNavItems: NavItem[] = [{ to: '/settings', label: 'Settings' }]

/** An item is active on its own path and on any sub-path (so Studio stays active whatever its query). */
function isItemActive(item: NavItem, pathname: string): boolean {
  return pathname === item.to || pathname.startsWith(`${item.to}/`)
}
function navLinkStyle({ isActive }: { isActive: boolean }): CSSProperties {
  return {
    padding: '6px 12px',
    textDecoration: 'none',
    fontSize: 'var(--text-base)',
    fontFamily: 'var(--font-sans)',
    color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
    background: isActive ? 'var(--bg-selected)' : 'transparent',
    borderRadius: 'var(--radius-sm)',
    fontWeight: isActive ? 500 : 400,
  }
}

/**
 * Compact horizontal top navigation (`frontend/AGENTS.md` §7.1-7.3).
 *
 * At narrow widths the primary links, Diagnosis & Recovery, and Settings
 * collapse into a single labelled menu button; every destination stays
 * reachable, the active destination stays visible, and the menu dismisses
 * on Escape, on navigating, or on returning to a desktop width.
 */
export function TopNavigation() {
  const isNarrow = useMediaQuery(NARROW_QUERY)
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()
  const menuId = useId()
  const user = useUser()

  const renderItem = (item: NavItem, onClick?: () => void) => {
    const active = isItemActive(item, location.pathname)
    return (
      <Link
        key={item.to}
        to={item.to}
        style={navLinkStyle({ isActive: active })}
        aria-current={active ? 'page' : undefined}
        onClick={onClick}
      >
        {item.label}
      </Link>
    )
  }

  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!isNarrow) setMenuOpen(false)
  }, [isNarrow])

  useEffect(() => {
    if (!menuOpen) return
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [menuOpen])

  return (
    <header
      style={{
        position: 'relative',
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
        <Link
          to="/"
          aria-label="RL Studio"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-3)',
            textDecoration: 'none',
            color: 'var(--text-primary)',
          }}
        >
          <LogoMark aria-hidden="true" width={24} height={24} />
          <span
            style={{
              fontSize: 'var(--text-md)',
              fontWeight: 600,
              fontFamily: 'var(--font-sans)',
            }}
          >
            RL Studio
          </span>
        </Link>
        {!isNarrow && (
          <nav
            aria-label="Primary"
            style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}
          >
            {primaryNavItems.map((item) => renderItem(item))}
          </nav>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-4)' }}>
        {!isNarrow && secondaryNavItems.map((item) => renderItem(item))}
        <ActiveProjectChip />
        <ThemeToggle />
        {user?.isSignedIn ? (
          <SignOutButton />
        ) : user?.isLoaded ? (
          <NavLink
            to="/login"
            style={{
              padding: '6px 12px',
              background: 'var(--bg-panel)',
              color: 'var(--text-primary)',
              textDecoration: 'none',
              border: '1px dashed var(--border-primary)',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              fontSize: 'var(--text-sm)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            Login
          </NavLink>
        ) : null}
        {isNarrow && (
          <button
            type="button"
            aria-expanded={menuOpen}
            aria-controls={menuId}
            aria-label={menuOpen ? 'Close navigation menu' : 'Open navigation menu'}
            onClick={() => setMenuOpen((open) => !open)}
            style={{
              padding: '6px 12px',
              background: 'var(--bg-panel)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              fontSize: 'var(--text-sm)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            Menu
          </button>
        )}
      </div>

      {isNarrow && menuOpen && (
        <nav
          id={menuId}
          aria-label="Primary"
          style={{
            position: 'absolute',
            top: '56px',
            left: 0,
            right: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '2px',
            padding: 'var(--space-2) var(--space-6)',
            background: 'var(--bg-header)',
            borderBottom: '1px solid var(--border-primary)',
            zIndex: 20,
          }}
        >
          {[...primaryNavItems, ...secondaryNavItems].map((item) =>
            renderItem(item, () => setMenuOpen(false)),
          )}
        </nav>
      )}
    </header>
  )
}
