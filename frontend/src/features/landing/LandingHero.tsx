import { Link } from 'react-router-dom'
import { ParticleScene } from './ParticleScene'
import { ArrowIcon } from './icons'

const delay = (ms: number) => ({ ['--d' as string]: `${ms}ms` })

export function LandingHero() {
  return (
    <section className="ls-hero" aria-labelledby="ls-headline">
      <div className="ls-hero__copy">
        <p className="ls-eyebrow ls-enter" style={delay(250)}>
          <span className="ls-eyebrow__dot" aria-hidden="true" />
          Self-healing RL, proven not guessed
        </p>

        <h1 id="ls-headline" className="ls-headline">
          <span className="ls-headline__line ls-enter" style={delay(400)}>
            Catch the fault
          </span>{' '}
          <span className="ls-headline__line ls-enter" style={delay(550)}>
            before it <em>trains in.</em>
          </span>
        </h1>

        <p className="ls-sub ls-enter" style={delay(700)}>
          RL Studio checks every run against developer-confirmed contracts, pins violations to real
          events, and only restores what it can verify.
        </p>

        <div className="ls-cta ls-enter" style={delay(800)}>
          <Link to="/projects" className="ls-pill ls-pill--solid">
            Open Studio
            <ArrowIcon className="ls-pill__arrow" />
          </Link>
          <Link to="/monitoring" className="ls-pill ls-pill--ghost">
            See canonical fault
          </Link>
        </div>

        <dl className="ls-proof ls-enter" style={delay(920)}>
          <div>
            <dt>Contracts</dt>
            <dd>Versioned, confirmed</dd>
          </div>
          <div>
            <dt>Evidence</dt>
            <dd>Events + checksums</dd>
          </div>
          <div>
            <dt>Recovery</dt>
            <dd>Verified before use</dd>
          </div>
        </dl>
      </div>

      <div className="ls-hero__scene">
        <ParticleScene />
      </div>
    </section>
  )
}
