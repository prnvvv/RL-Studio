/** Reports-specific glyphs. The section icons live in the shared set (MonitoringIcon). */
export function SearchGlyph() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className="rp-filter__icon">
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14" />
    </svg>
  )
}

/** Stacked archive trays: the empty state for a history that has no records. */
export function ArchiveArt() {
  return (
    <svg viewBox="0 0 56 56" aria-hidden="true" className="rp-empty__art">
      <rect x="9" y="12" width="38" height="9" rx="2" strokeOpacity="0.9" />
      <rect x="9" y="24" width="38" height="9" rx="2" strokeOpacity="0.6" />
      <rect x="9" y="36" width="38" height="9" rx="2" strokeOpacity="0.35" strokeDasharray="2 3" />
      <path d="M15 16.5h8M15 28.5h8" strokeOpacity="0.7" />
    </svg>
  )
}

/** Two balanced columns joined by a dotted baseline: the empty state for a comparison. */
export function CompareArt() {
  return (
    <svg viewBox="0 0 56 56" aria-hidden="true" className="rp-empty__art">
      <rect x="11" y="22" width="12" height="22" rx="2" strokeOpacity="0.85" />
      <rect
        x="33"
        y="14"
        width="12"
        height="30"
        rx="2"
        strokeOpacity="0.55"
        strokeDasharray="2 3"
      />
      <path d="M6 47h44" strokeOpacity="0.4" strokeDasharray="1 3" />
    </svg>
  )
}
