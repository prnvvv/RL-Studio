import { Link } from 'react-router-dom'
import { ParticleScene } from './ParticleScene'
import { ArrowIcon, PlayIcon } from './icons'

const delay = (ms: number) => ({ ['--d' as string]: `${ms}ms` })

export function LandingHero() {
  return (
    <section className="ls-hero" aria-labelledby="ls-headline">
      <div className="ls-hero__copy">
        <p className="ls-eyebrow ls-enter" style={delay(250)}>
          <span className="ls-eyebrow__dot" aria-hidden="true" />
          Simulate <span aria-hidden="true">•</span> Detect <span aria-hidden="true">•</span>{' '}
          Recover <span aria-hidden="true">•</span> Improve
        </p>

        <h1 id="ls-headline" className="ls-headline">
          <span className="ls-headline__line ls-enter" style={delay(400)}>
            A safer sandbox
          </span>{' '}
          <span className="ls-headline__line ls-enter" style={delay(550)}>
            for <em>stronger</em> agents.
          </span>
        </h1>

        <div className="ls-cta ls-enter" style={delay(750)}>
          <Link to="/projects" className="ls-pill ls-pill--solid">
            Open Studio
            <ArrowIcon className="ls-pill__arrow" />
          </Link>
          <Link to="/monitoring" className="ls-pill ls-pill--ghost">
            <PlayIcon />
            Watch Demo
          </Link>
        </div>
      </div>

      <div className="ls-hero__scene">
        <ParticleScene />
      </div>
    </section>
  )
}
