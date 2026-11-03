import { Link } from 'react-router-dom'
import { FeatureStrip } from '../features/landing/FeatureStrip'
import { LandingHero } from '../features/landing/LandingHero'
import { LandingNavbar } from '../features/landing/LandingNavbar'
import '../features/landing/landing.css'

// The landing page is intentionally a standalone dark surface: it does not use
// ApplicationShell or the app theme tokens, and it makes no run-data claims.
const pillars = [
  {
    title: 'Fault detection',
    body: 'Compare execution against developer-confirmed contracts and flag violations with evidence.',
    to: '/monitoring',
    cta: 'Open monitoring',
  },
  {
    title: 'Experience provenance',
    body: 'Trace which experiences, updates and checkpoints a fault may have touched, and where lineage is unknown.',
    to: '/diagnosis-recovery',
    cta: 'Open diagnosis',
  },
  {
    title: 'Adaptive recovery',
    body: 'Validate a supported recovery action, then evaluate the result before calling it a success.',
    to: '/reports',
    cta: 'Open reports',
  },
]

export function HomePage() {
  return (
    <div className="ls-root">
      <div className="ls-first-screen">
        <LandingNavbar />
        <main className="ls-main">
          <LandingHero />
        </main>
        <FeatureStrip />
      </div>

      <section id="overview" className="ls-overview" aria-labelledby="ls-overview-title">
        <h2 id="ls-overview-title" className="ls-overview__title">
          From fault to verified recovery
        </h2>
        <div className="ls-overview__grid">
          {pillars.map((pillar) => (
            <article key={pillar.title} className="ls-overview__card">
              <h3>{pillar.title}</h3>
              <p>{pillar.body}</p>
              <Link to={pillar.to} className="ls-overview__link">
                {pillar.cta}
              </Link>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}
