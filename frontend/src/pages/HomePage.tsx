import type { ComponentType, SVGProps } from 'react'
import { Link } from 'react-router-dom'
import { WakeGlyph } from '../components/ui/background-ascii-wake'
import { AmbientWaves } from '../features/landing/AmbientWaves'
import { FeatureStrip } from '../features/landing/FeatureStrip'
import { CubeIcon, CycleIcon, PulseIcon } from '../features/landing/icons'
import { LandingHero } from '../features/landing/LandingHero'
import { LandingNavbar } from '../features/landing/LandingNavbar'
import { TechStrip } from '../features/landing/TechStrip'
import { TelemetrySection } from '../features/landing/TelemetrySection'
import { useReveal } from '../features/landing/useReveal'
import '../features/landing/landing.css'
import '../features/landing/landing.sections.css'

// The landing page is intentionally a standalone dark surface: it does not use
// ApplicationShell or the app theme tokens, and it makes no run-data claims.
interface Pillar {
  title: string
  body: string
  to: string
  cta: string
  Icon: ComponentType<SVGProps<SVGSVGElement>>
}

const pillars: Pillar[] = [
  {
    title: 'Fault detection',
    body: 'Compare execution against developer-confirmed contracts and flag violations with evidence.',
    to: '/monitoring',
    cta: 'Open monitoring',
    Icon: PulseIcon,
  },
  {
    title: 'Experience provenance',
    body: 'Trace which experiences, updates and checkpoints a fault may have touched, and where lineage is unknown.',
    to: '/diagnosis-recovery',
    cta: 'Open diagnosis',
    Icon: CubeIcon,
  },
  {
    title: 'Adaptive recovery',
    body: 'Validate a supported recovery action, then evaluate the result before calling it a success.',
    to: '/reports',
    cta: 'Open reports',
    Icon: CycleIcon,
  },
]

function PillarCard({ pillar, index }: { pillar: Pillar; index: number }) {
  const { ref, visible } = useReveal<HTMLElement>(0.25)
  const { Icon } = pillar
  return (
    <article
      ref={ref}
      className="ls-overview__card"
      data-reveal=""
      data-in={visible ? '' : undefined}
      style={{ ['--i' as string]: index }}
    >
      <span className="ls-overview__icon" aria-hidden="true">
        <Icon width={20} height={20} />
      </span>
      <h3>{pillar.title}</h3>
      <p>{pillar.body}</p>
      <Link to={pillar.to} className="ls-overview__link">
        {pillar.cta}
        <span className="ls-overview__arrow" aria-hidden="true">
          →
        </span>
      </Link>
    </article>
  )
}

export function HomePage() {
  return (
    <div className="ls-root">
      <div className="ls-first-screen">
        <WakeGlyph className="ls-wake" cellSize={18} />
        <AmbientWaves />
        <LandingNavbar />
        <main className="ls-main">
          <LandingHero />
        </main>
        <FeatureStrip />
      </div>

      <div className="ls-bridge" aria-hidden="true" />
      <TelemetrySection />
      <TechStrip />

      <section id="overview" className="ls-overview" aria-labelledby="ls-overview-title">
        <h2 id="ls-overview-title" className="ls-overview__title">
          From fault to verified recovery
        </h2>
        <div className="ls-overview__grid">
          {pillars.map((pillar, index) => (
            <PillarCard key={pillar.title} pillar={pillar} index={index} />
          ))}
        </div>
      </section>
    </div>
  )
}
