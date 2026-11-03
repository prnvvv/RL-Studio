import { ChevronDownIcon, CubeIcon, CycleIcon, PulseIcon, SparkleIcon } from './icons'

const features = [
  { id: 'detection', label: 'Fault Detection', Icon: PulseIcon },
  { id: 'provenance', label: 'Experience Provenance', Icon: CubeIcon },
  { id: 'recovery', label: 'Adaptive Recovery', Icon: CycleIcon },
]

function scrollToOverview() {
  const reduced =
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  document
    .getElementById('telemetry')
    ?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
}

export function FeatureStrip() {
  return (
    <div className="ls-bottom ls-enter" style={{ ['--d' as string]: '950ms' }}>
      <ul className="ls-strip" aria-label="Platform capabilities">
        {features.map(({ id, label, Icon }) => (
          <li key={id} className="ls-strip__item">
            <span className="ls-strip__icon" aria-hidden="true">
              <Icon />
            </span>
            <span className="ls-strip__label">{label}</span>
          </li>
        ))}
      </ul>

      <div className="ls-bottom__row">
        <button
          type="button"
          className="ls-scroll"
          aria-label="Scroll to overview"
          onClick={scrollToOverview}
        >
          <ChevronDownIcon />
        </button>
        <SparkleIcon className="ls-sparkle" />
      </div>
    </div>
  )
}
