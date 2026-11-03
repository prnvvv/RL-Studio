import type { ReactNode } from 'react'
import { InfoTip } from '../InfoTip'

interface Props {
  title: string
  /** What this metric tells a researcher; shown behind a `?`. */
  hint?: string
  /** The most recent value, if any. */
  value?: string | null
  control?: ReactNode
  children: ReactNode
}

export function ChartCard({ title, hint, value, control, children }: Props) {
  return (
    <section className="chart-card chart-card--panel" aria-label={title}>
      <header className="chart-card__head">
        <h4>{title}</h4>
        {hint && <InfoTip label={`About ${title}`}>{hint}</InfoTip>}
        {value != null && <output className="chart-card__value">{value}</output>}
        {control}
      </header>
      {children}
    </section>
  )
}

/** A collapsible group of related charts. */
export function MetricSection({
  title,
  children,
  open = true,
}: {
  title: string
  children: ReactNode
  open?: boolean
}) {
  return (
    <details className="metric-section" open={open}>
      <summary>{title}</summary>
      <div className="metric-section__body">{children}</div>
    </details>
  )
}
