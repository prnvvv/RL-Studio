/**
 * Empty state for an unscoped Monitoring page: three floating translucent layers over a dotted
 * orbit, with a few vertical markers. Purely illustrative; it carries no data.
 */
export function NoRunSelected() {
  return (
    <div role="status" className="mon-empty">
      <svg
        className="mon-empty__art"
        viewBox="0 0 260 170"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
      >
        {/* Dotted orbit under the stack */}
        <ellipse
          cx="130"
          cy="132"
          rx="104"
          ry="26"
          strokeOpacity="0.35"
          strokeWidth="1"
          strokeDasharray="1.5 5"
          strokeLinecap="round"
        />
        {/* Vertical markers with circular endpoints */}
        <g strokeOpacity="0.3" strokeWidth="1">
          <path d="M44 124V92" />
          <path d="M216 124V78" />
          <path d="M130 158V138" />
        </g>
        <g fill="currentColor" fillOpacity="0.45" stroke="none">
          <circle cx="44" cy="90" r="2.5" />
          <circle cx="216" cy="76" r="2.5" />
          <circle cx="130" cy="160" r="2" />
        </g>
        {/* Three floating layers, lowest first */}
        <path
          d="M130 78l62 28-62 28-62-28z"
          fill="currentColor"
          fillOpacity="0.04"
          strokeOpacity="0.35"
        />
        <path
          d="M130 56l62 28-62 28-62-28z"
          fill="currentColor"
          fillOpacity="0.07"
          strokeOpacity="0.55"
        />
        <path
          d="M130 34l62 28-62 28-62-28z"
          fill="currentColor"
          fillOpacity="0.1"
          strokeOpacity="0.85"
        />
        {/* Soft highlight on the top face */}
        <path d="M100 56l30-13" strokeOpacity="0.9" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <span className="mon-empty__title">No run selected</span>
      <span className="mon-empty__description">
        Enter a run identifier to subscribe to that run&apos;s recorded events. Nothing is inferred
        for an unscoped page.
      </span>
    </div>
  )
}
