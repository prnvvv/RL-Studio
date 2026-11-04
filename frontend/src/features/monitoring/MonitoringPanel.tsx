import type { ReactNode } from 'react'

export type MonitoringIconName =
  'layers' | 'chart' | 'target' | 'pulse' | 'link' | 'lifecycle' | 'info' | 'history' | 'compare'

/** Minimal monochrome line icons, drawn with the same stroke conventions as the stat icons. */
export function MonitoringIcon({
  name,
  className,
}: {
  name: MonitoringIconName
  className?: string
}) {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className={className ?? 'mon-icon'}>
      {name === 'layers' && (
        <>
          <path d="M10 3l7 3.5-7 3.5-7-3.5z" />
          <path d="M3 10l7 3.5 7-3.5" />
          <path d="M3 13.5L10 17l7-3.5" />
        </>
      )}
      {name === 'chart' && (
        <>
          <path d="M4 16V9" />
          <path d="M10 16V4" />
          <path d="M16 16v-5" />
        </>
      )}
      {name === 'target' && (
        <>
          <circle cx="10" cy="10" r="7" />
          <circle cx="10" cy="10" r="3.5" />
          <circle cx="10" cy="10" r="0.6" />
        </>
      )}
      {name === 'pulse' && <path d="M2 10h4l2-5 4 10 2-5h4" />}
      {name === 'link' && (
        <>
          <path d="M8.5 11.5l3-3" />
          <path d="M11 6.5l1-1a3 3 0 014.2 4.2l-1 1" />
          <path d="M9 13.5l-1 1a3 3 0 01-4.2-4.2l1-1" />
        </>
      )}
      {name === 'lifecycle' && (
        <>
          <circle cx="10" cy="10" r="7" />
          <path d="M10 6v4l2.5 1.5" />
        </>
      )}
      {name === 'history' && (
        <>
          <path d="M3 10a7 7 0 107-7 7.2 7.2 0 00-5 2.1" />
          <path d="M3 3.5v3h3" />
          <path d="M10 6.5V10l2.5 1.5" />
        </>
      )}
      {name === 'compare' && (
        <>
          <path d="M4 16V9" />
          <path d="M8 16V5" />
          <path d="M13 16v-4" />
          <path d="M17 16V7" />
          <path d="M3 16.5h15" />
        </>
      )}
      {name === 'info' && (
        <>
          <circle cx="10" cy="10" r="7" />
          <path d="M10 9v4.5" />
          <circle cx="10" cy="6.5" r="0.4" />
        </>
      )}
    </svg>
  )
}

interface MonitoringPanelProps {
  title: string
  description?: string
  icon?: MonitoringIconName
  actions?: ReactNode
  footer?: ReactNode
  children: ReactNode
}

/**
 * Monitoring's panel surface. Same contract as the shared `Panel` (a labelled region with a
 * title, description and footer), restyled for this page without changing the shared component
 * that other pages use.
 */
export function MonitoringPanel({
  title,
  description,
  icon,
  actions,
  footer,
  children,
}: MonitoringPanelProps) {
  return (
    <section className="mon-panel" aria-label={title}>
      <header className="mon-panel__header">
        <div className="mon-panel__heading">
          {icon ? <MonitoringIcon name={icon} /> : null}
          <div className="mon-panel__titles">
            <h2 className="mon-panel__title">{title}</h2>
            {description ? <p className="mon-panel__description">{description}</p> : null}
          </div>
        </div>
        {actions ? <div style={{ flexShrink: 0 }}>{actions}</div> : null}
      </header>
      <div className="mon-panel__body">{children}</div>
      {footer ? <footer className="mon-panel__footer">{footer}</footer> : null}
    </section>
  )
}
