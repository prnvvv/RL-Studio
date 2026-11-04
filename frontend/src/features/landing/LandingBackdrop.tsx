import type { ReactNode } from 'react'
import { WakeGlyph } from '../../components/ui/background-ascii-wake'
import { AmbientWaves } from './AmbientWaves'

interface LandingBackdropProps {
  /** Extra class for a host page that needs to reposition the same backdrop (e.g. fixed behind scrolling content). */
  className?: string
  children?: ReactNode
}

/**
 * The landing page's first-screen background: the `ls-first-screen` surface (gradients and drifting dust) with
 * the ASCII wake and the ambient wave canvas. The landing page and the Project Dashboard both render this one
 * component, so the dashboard is the same background, not a lookalike. Must sit inside `.ls-root`.
 */
export function LandingBackdrop({ className = '', children }: LandingBackdropProps) {
  return (
    <div className={`ls-first-screen ${className}`.trim()}>
      <WakeGlyph className="ls-wake" cellSize={16} />
      <AmbientWaves />
      {children}
    </div>
  )
}
