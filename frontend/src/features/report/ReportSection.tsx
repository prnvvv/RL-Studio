import type { ReactNode } from 'react'
import { Panel } from '../../components/ui/Panel'
import { LoadingSkeleton } from '../../components/ui/LoadingSkeleton'
import { UnavailableState } from '../../components/ui/UnavailableState'
import { ErrorState } from '../../components/ui/ErrorState'
import { StatusBadge, type StatusGlyph, type StatusTone } from '../../components/ui/StatusBadge'

/**
 * A report section's status is independent from whatever loading/error
 * handling its own underlying panel already does internally. This status
 * answers one question only: is this domain connected and in scope for the
 * focused run at all?
 *
 * - `not_applicable`: this run has no connected scope for the domain (for
 *   example no incident identifier), so there is genuinely nothing to show —
 *   this is not a failure.
 * - `unavailable`: the capability itself has no run-scoped contract yet, a
 *   documented backend gap rather than a missing connection.
 * - `failed`: an explicit fetch this section owns did not succeed.
 * - `success`: the section is connected; its own content (which may still
 *   load, retain stale data, or show an inner error) is rendered as children.
 */
export type ReportSectionStatus =
  | { kind: 'pending' }
  | { kind: 'not_applicable'; description: string }
  | { kind: 'unavailable'; description: string; owner?: string }
  | { kind: 'failed'; description: string; onRetry?: () => void }
  | { kind: 'success' }

export interface ReportSectionProps {
  title: string
  description?: string
  status: ReportSectionStatus
  /** Rendered only when `status.kind === 'success'`. */
  children?: ReactNode
}

const STATUS_BADGE: Record<
  ReportSectionStatus['kind'],
  { label: string; tone: StatusTone; glyph: StatusGlyph }
> = {
  pending: { label: 'Loading', tone: 'quiet', glyph: 'dot' },
  not_applicable: { label: 'Not applicable', tone: 'quiet', glyph: 'none' },
  unavailable: { label: 'Unavailable', tone: 'quiet', glyph: 'query' },
  failed: { label: 'Failed', tone: 'strong', glyph: 'cross' },
  success: { label: 'Loaded', tone: 'neutral', glyph: 'check' },
}

const retryButtonStyle = {
  padding: '6px 14px',
  background: 'var(--bg-input)',
  border: '1px solid var(--border-primary)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
  fontFamily: 'var(--font-sans)',
} as const

/**
 * Independently-loading report section shell (Phase 6). Every section of the
 * unified diagnostic report renders through this so one section's
 * inapplicability, unavailability, or failure can never block the others,
 * and so "loaded", "not applicable", "unavailable", and "failed" stay
 * visually and textually distinct instead of collapsing into a blank panel.
 */
export function ReportSection({ title, description, status, children }: ReportSectionProps) {
  const badge = STATUS_BADGE[status.kind]

  return (
    <Panel
      title={title}
      description={description}
      actions={<StatusBadge label={badge.label} tone={badge.tone} glyph={badge.glyph} />}
    >
      {status.kind === 'pending' && <LoadingSkeleton rows={3} />}
      {status.kind === 'not_applicable' && (
        <UnavailableState title="Not applicable to this run" description={status.description} />
      )}
      {status.kind === 'unavailable' && (
        <UnavailableState
          title="Section unavailable"
          description={status.description}
          owner={status.owner}
        />
      )}
      {status.kind === 'failed' && (
        <ErrorState
          title="This section could not be loaded"
          description={status.description}
          action={
            status.onRetry ? (
              <button type="button" onClick={status.onRetry} style={retryButtonStyle}>
                Retry
              </button>
            ) : undefined
          }
        />
      )}
      {status.kind === 'success' && children}
    </Panel>
  )
}
