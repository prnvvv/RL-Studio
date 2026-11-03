import type { ReactElement, SVGProps } from 'react'
import { useReveal } from './useReveal'

const glyph: SVGProps<SVGSVGElement> = {
  viewBox: '0 0 24 24',
  width: 16,
  height: 16,
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.4,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
  focusable: false,
}

/**
 * The stack RL Studio is actually built on. Each name is a dependency pinned in the project
 * (requirements.txt): stable_baselines3, torch, gymnasium and fastapi. The icons are generic
 * monochrome glyphs, not the products' logos.
 */
const TECH: Array<{ name: string; icon: ReactElement }> = [
  {
    name: 'Stable-Baselines3',
    icon: (
      <svg {...glyph}>
        <path d="m12 3 8 4.5-8 4.5-8-4.5z" />
        <path d="m4 12 8 4.5 8-4.5M4 16.5 12 21l8-4.5" />
      </svg>
    ),
  },
  {
    name: 'PyTorch',
    icon: (
      <svg {...glyph}>
        <rect x="4" y="4" width="6.5" height="6.5" rx="1.2" />
        <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.2" />
        <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.2" />
        <path d="M13.5 16.75h6.5M16.75 13.5V20" />
      </svg>
    ),
  },
  {
    name: 'Gymnasium',
    icon: (
      <svg {...glyph}>
        <path d="M4 4h16v16H4z" />
        <path d="M4 9.5h9.5V15H20M9.5 4v5.5M14 15v5" />
      </svg>
    ),
  },
  {
    name: 'FastAPI',
    icon: (
      <svg {...glyph}>
        <path d="M13 3 5 13.5h6L10 21l9-11h-6.2z" />
      </svg>
    ),
  },
]

export function TechStrip() {
  const { ref, visible } = useReveal<HTMLElement>(0.4)
  return (
    <section
      ref={ref}
      className="ls-tech"
      aria-label="Technology stack"
      data-reveal=""
      data-in={visible ? '' : undefined}
    >
      <div className="ls-tech__row">
        <span className="ls-tech__label">Built with</span>
        <ul className="ls-tech__list">
          {TECH.map(({ name, icon }) => (
            <li key={name} className="ls-tech__item">
              {icon}
              <span>{name}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
