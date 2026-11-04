import { Link } from 'react-router-dom'
import { ArrowIcon } from './icons'
import { useReveal } from './useReveal'

export function FooterCTA() {
  const { ref, visible } = useReveal<HTMLDivElement>(0.25)
  return (
    <footer className="ls-footer" aria-labelledby="ls-footer-title">
      <div className="ls-footer__wrap" ref={ref} data-reveal="" data-in={visible ? '' : undefined}>
        <p className="ls-kicker">Start in minutes</p>
        <h2 id="ls-footer-title" className="ls-footer__title">
          Train with a <em>safety net</em> under every run.
        </h2>
        <p className="ls-footer__sub">
          Create a project, confirm the contract, run seeded PPO, and let the evidence do the
          talking.
        </p>
        <div className="ls-footer__cta">
          <Link to="/projects" className="ls-pill ls-pill--solid">
            Open Studio
            <ArrowIcon className="ls-pill__arrow" />
          </Link>
          <Link to="/reports" className="ls-pill ls-pill--ghost">
            View reports
          </Link>
        </div>
        <p className="ls-footer__meta">
          Self-Healing RL Studio · PPO via Stable-Baselines3 · Warehouse 2D demo
        </p>
      </div>
    </footer>
  )
}
