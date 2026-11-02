import { formatUtcDate, formatUtcTime } from '../../utils/datetime'

/**
 * Event categories are a *presentation* mapping, not an API contract. The
 * mapping from backend event types is unconfirmed (TODO T-1004), so this
 * component accepts an explicit category and falls back to `unknown`.
 */
export type EventCategory =
  'observation' | 'verification' | 'diagnosis' | 'recovery' | 'evaluation' | 'unknown'

export interface TimelineEvent {
  id: string
  /**
   * ISO-8601 timestamp as recorded by the backend, or `null` when the record
   * carries no timestamp. A missing time renders as "Not recorded" instead of
   * a placeholder clock value.
   */
  timestamp: string | null
  category: EventCategory
  title: string
  detail?: string
  /** Source component or detector name, when recorded. */
  source?: string
}

const categoryLabel: Record<EventCategory, string> = {
  observation: 'Observation',
  verification: 'Verification',
  diagnosis: 'Diagnosis',
  recovery: 'Recovery',
  evaluation: 'Evaluation',
  unknown: 'Unclassified',
}

/** Marker shapes differ per category so events are not distinguished by colour. */
function CategoryMarker({ category }: { category: EventCategory }) {
  const base = {
    width: '9px',
    height: '9px',
    border: '1px solid var(--text-primary)',
    background: 'transparent',
  } as const

  switch (category) {
    case 'observation':
      return <span aria-hidden="true" style={{ ...base, borderRadius: '50%' }} />
    case 'verification':
      return (
        <span
          aria-hidden="true"
          style={{ ...base, borderRadius: '50%', background: 'var(--text-primary)' }}
        />
      )
    case 'diagnosis':
      return <span aria-hidden="true" style={{ ...base, transform: 'rotate(45deg)' }} />
    case 'recovery':
      return <span aria-hidden="true" style={{ ...base, background: 'var(--text-primary)' }} />
    case 'evaluation':
      return (
        <span
          aria-hidden="true"
          style={{
            ...base,
            borderRadius: 'var(--radius-sm)',
            borderStyle: 'double',
            borderWidth: '3px',
          }}
        />
      )
    case 'unknown':
    default:
      return <span aria-hidden="true" style={{ ...base, borderStyle: 'dashed' }} />
  }
}

interface EventTimelineProps {
  events: TimelineEvent[]
  /** Total number of recorded events, when larger than `events` (bounded window). */
  totalCount?: number
}

export function EventTimeline({ events, totalCount }: EventTimelineProps) {
  if (events.length === 0) {
    return null
  }

  return (
    <div>
      <ol
        aria-label="Recorded execution events, most recent first"
        style={{ listStyle: 'none', margin: 0, padding: 0 }}
      >
        {events.map((event, index) => {
          const time = event.timestamp === null ? null : formatUtcTime(event.timestamp)
          const date = event.timestamp === null ? null : formatUtcDate(event.timestamp)

          return (
            <li
              key={event.id}
              style={{
                display: 'grid',
                gridTemplateColumns: '58px 12px minmax(0, 1fr)',
                gap: 'var(--space-3)',
                padding: 'var(--space-3) 0',
                borderTop: index === 0 ? 'none' : '1px solid var(--border-secondary)',
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
                {event.timestamp === null ? (
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '10px',
                      color: 'var(--text-muted)',
                    }}
                  >
                    Not recorded
                  </span>
                ) : (
                  <time
                    dateTime={event.timestamp}
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 'var(--text-xs)',
                      color: 'var(--text-secondary)',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {time ?? 'Invalid time'}
                  </time>
                )}
                {date ? (
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: '10px',
                      color: 'var(--text-muted)',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {date}
                  </span>
                ) : null}
              </div>

              <div
                aria-hidden="true"
                style={{
                  position: 'relative',
                  display: 'flex',
                  justifyContent: 'center',
                  paddingTop: '3px',
                }}
              >
                {index !== events.length - 1 ? (
                  <span
                    style={{
                      position: 'absolute',
                      top: '14px',
                      bottom: '-13px',
                      width: '1px',
                      background: 'var(--border-primary)',
                    }}
                  />
                ) : null}
                <CategoryMarker category={event.category} />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'baseline',
                    gap: 'var(--space-2)',
                    flexWrap: 'wrap',
                  }}
                >
                  <span
                    style={{
                      fontSize: '10px',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      color: 'var(--text-muted)',
                      fontFamily: 'var(--font-sans)',
                    }}
                  >
                    {categoryLabel[event.category]}
                  </span>
                  {event.source ? (
                    <span
                      style={{
                        fontSize: '10px',
                        color: 'var(--text-muted)',
                        fontFamily: 'var(--font-mono)',
                      }}
                    >
                      {event.source}
                    </span>
                  ) : null}
                </div>
                <span
                  style={{
                    fontSize: 'var(--text-sm)',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-sans)',
                    overflowWrap: 'anywhere',
                  }}
                >
                  {event.title}
                </span>
                {event.detail ? (
                  <span
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--text-secondary)',
                      fontFamily: 'var(--font-sans)',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    {event.detail}
                  </span>
                ) : null}
                <span
                  style={{
                    fontSize: '10px',
                    color: 'var(--text-muted)',
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {event.id}
                </span>
              </div>
            </li>
          )
        })}
      </ol>
      {totalCount !== undefined && totalCount > events.length ? (
        <p
          style={{
            margin: 'var(--space-3) 0 0 0',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          Showing {events.length} of {totalCount} recorded events.
        </p>
      ) : null}
    </div>
  )
}
