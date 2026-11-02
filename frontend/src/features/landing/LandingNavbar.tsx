import { Link } from 'react-router-dom'
import { ArrowIcon, LogoMark } from './icons'

// Platform and Research point at existing app pages; Team has no page yet, so
// it scrolls to the overview section rather than linking to a dead route.
const navLinks: Array<{ label: string; to?: string; href?: string }> = [
  { to: '/environments', label: 'Platform' },
  { to: '/reports', label: 'Research' },
  { href: '#overview', label: 'Team' },
]

export function LandingNavbar() {
  return (
    <header className="ls-nav ls-enter" style={{ ['--d' as string]: '0ms' }}>
      <div className="ls-nav__brand">
        <Link to="/" className="ls-nav__logo" aria-label="RL Studio home">
          <LogoMark />
          <span>RL Studio</span>
        </Link>
        <span className="ls-nav__divider" aria-hidden="true" />
        <span className="ls-nav__tagline">Self-healing reinforcement learning</span>
      </div>

      <nav className="ls-nav__links" aria-label="Primary">
        {navLinks.map((link) =>
          link.to ? (
            <Link key={link.label} to={link.to} className="ls-nav__link">
              {link.label}
            </Link>
          ) : (
            <a key={link.label} href={link.href} className="ls-nav__link">
              {link.label}
            </a>
          ),
        )}
        <Link to="/training" className="ls-pill ls-pill--solid ls-pill--sm">
          Open Studio
          <ArrowIcon className="ls-pill__arrow" />
        </Link>
      </nav>
    </header>
  )
}
