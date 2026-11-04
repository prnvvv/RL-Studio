import { Link } from 'react-router-dom'
import { ArrowIcon } from './icons'
import { useReveal } from './useReveal'

const STEPS = [
  {
    n: '01',
    title: 'Confirm',
    body: 'Lock requirements and env config with a seed. Fingerprint the config, agent and run.',
    to: '/projects',
    cta: 'Create project',
  },
  {
    n: '02',
    title: 'Train',
    body: 'Seeded PPO run records canonical events and atomic, checksummed checkpoints.',
    to: '/studio',
    cta: 'Open Studio',
  },
  {
    n: '03',
    title: 'Detect',
    body: 'Requirements are evaluated against real evidence — incidents cite event IDs.',
    to: '/monitoring',
    cta: 'Open monitoring',
  },
  {
    n: '04',
    title: 'Recover',
    body: 'Trace exposure, restore a compatible checkpoint, collect fresh on-policy experience.',
    to: '/diagnosis-recovery',
    cta: 'Diagnosis & recovery',
  },
  {
    n: '05',
    title: 'Prove',
    body: 'Evaluate the recovered policy against baselines and report measured outcomes.',
    to: '/reports',
    cta: 'View reports',
  },
] as const

export function WorkflowSteps() {
  const { ref, visible } = useReveal<HTMLDivElement>(0.18)
  return (
    <section className="ls-workflow" aria-labelledby="ls-workflow-title">
      <div className="ls-workflow__head">
        <p className="ls-kicker">Workflow</p>
        <h2 id="ls-workflow-title" className="ls-workflow__title">
          From fault to <em>verified</em> recovery
        </h2>
      </div>

      <div
        ref={ref}
        className="ls-workflow__list"
        data-reveal=""
        data-in={visible ? '' : undefined}
      >
        {STEPS.map((step, i) => (
          <article key={step.n} className="ls-workflow__row" style={{ ['--i' as string]: i }}>
            <span className="ls-workflow__n" aria-hidden="true">
              {step.n}
            </span>
            <div className="ls-workflow__body">
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </div>
            <Link to={step.to} className="ls-workflow__cta">
              {step.cta}
              <ArrowIcon className="ls-workflow__arrow" />
            </Link>
          </article>
        ))}
      </div>
    </section>
  )
}
