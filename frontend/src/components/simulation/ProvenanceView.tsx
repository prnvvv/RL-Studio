/**
 * Provenance and incident-impact display (Person 4's live endpoints).
 *
 * Renders the recorded provenance trace (`GET /api/v1/runs/{run_id}/provenance`)
 * and the incident impact analysis (`GET /api/v1/incidents/{incident_id}/impact`)
 * for a focused incident. Everything shown comes from the record; the
 * component never reclassifies or derives status.
 *
 * Hard presentation rules (frontend/AGENTS.md §14.1):
 * - The four impact classifications are four distinct claims. In particular
 *   `unknown_incomplete_lineage` is rendered as UNKNOWN with an explicit
 *   explanation and is never visually or verbally merged with
 *   "not exposed based on recorded lineage".
 * - Exposure is never upgraded to damage: recorded classifications are shown
 *   verbatim alongside their qualifier.
 */
import { StatusBadge } from '../ui/StatusBadge'
import { ErrorState } from '../ui/ErrorState'
import { LoadingSkeleton } from '../ui/LoadingSkeleton'
import { MOCK_DATA_LABEL, type MockData, unwrapMockData } from '../../mocks'
import type { ImpactAnalysis, ProvenanceTrace } from '../../schemas/provenance'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'

/** Query state whose payloads may be mock-wrapped (each carries its label). */
type PanelState<T> = ServiceQueryState<T | MockData<T>>

const listStyle = {
  listStyle: 'none',
  margin: 0,
  padding: 0,
} as const

const detailText = {
  margin: 0,
  fontSize: 'var(--text-xs)',
  color: 'var(--text-secondary)',
  fontFamily: 'var(--font-sans)',
  lineHeight: 1.6,
} as const

const TRACE_STATUS_LABELS: Record<ProvenanceTrace['provenance_status'], string> = {
  complete: 'Provenance: complete',
  incomplete: 'Provenance: incomplete',
  unknown: 'Provenance: unknown',
  conflict: 'Provenance: conflict detected',
}

const LINEAGE_LABELS: Record<ProvenanceTrace['lineage_completeness'], string> = {
  complete: 'Lineage: complete',
  partial: 'Lineage: partial',
  unknown: 'Lineage: unknown',
}

/**
 * The four impact classifications as four distinct presentations. The
 * `unknown_incomplete_lineage` qualifier ("impact unknown") is part of the
 * contractual wording: an unknown classification is NOT an unaffected claim.
 */
const IMPACT_PRESENTATIONS: Record<
  ImpactAnalysis['impact_status'],
  {
    label: string
    tone: 'neutral' | 'strong' | 'quiet'
    glyph: 'cross' | 'dot' | 'check' | 'query'
    note?: string
  }
> = {
  confirmed_exposed: { label: 'Impact: confirmed exposed', tone: 'strong', glyph: 'cross' },
  potentially_affected: { label: 'Impact: potentially affected', tone: 'neutral', glyph: 'dot' },
  not_exposed_based_on_recorded_lineage: {
    label: 'Not exposed based on recorded lineage',
    tone: 'quiet',
    glyph: 'check',
  },
  unknown_incomplete_lineage: {
    label: 'Impact unknown — incomplete lineage',
    tone: 'quiet',
    glyph: 'query',
    note: 'not an unaffected claim',
  },
}

/** One recorded artifact as a dense row. */
function ArtifactRow({
  index,
  artifact,
}: {
  index: number
  artifact: ProvenanceTrace['artifacts'][number]
}) {
  return (
    <li
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 2fr) auto',
        gap: 'var(--space-3)',
        alignItems: 'start',
        padding: 'var(--space-2) 0',
        borderTop: index === 0 ? 'none' : '1px solid var(--border-secondary)',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
        <span
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
            overflowWrap: 'anywhere',
          }}
        >
          {artifact.artifact_id}
        </span>
        <span
          style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          {artifact.artifact_type}
          {artifact.environment_version ? ` · env ${artifact.environment_version}` : ''}
          {artifact.checkpoint_id ? ` · checkpoint ${artifact.checkpoint_id}` : ''}
        </span>
      </div>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-end',
          gap: 'var(--space-1)',
        }}
      >
        <StatusBadge label={`Artifact: ${artifact.artifact_status}`} tone="neutral" glyph="none" />
        <StatusBadge label={`Integrity: ${artifact.integrity_status}`} tone="quiet" glyph="none" />
      </div>
    </li>
  )
}

/** The loaded trace content: status badges, artifacts, links, warnings. */
function LoadedTrace({ trace, labeled }: { trace: ProvenanceTrace; labeled: boolean }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div
        style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', alignItems: 'center' }}
      >
        <StatusBadge
          label={TRACE_STATUS_LABELS[trace.provenance_status]}
          tone={trace.provenance_status === 'complete' ? 'neutral' : 'quiet'}
          glyph={trace.provenance_status === 'complete' ? 'check' : 'query'}
        />
        <StatusBadge
          label={LINEAGE_LABELS[trace.lineage_completeness]}
          tone={trace.lineage_completeness === 'complete' ? 'quiet' : 'quiet'}
          glyph={trace.lineage_completeness === 'complete' ? 'check' : 'dot'}
        />
        {labeled && <StatusBadge label={MOCK_DATA_LABEL} tone="quiet" glyph="dot" />}
      </div>

      <section aria-label="Recorded artifacts">
        <h4
          style={{
            margin: '0 0 var(--space-2) 0',
            fontSize: 'var(--text-xs)',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          Recorded artifacts ({trace.artifacts.length})
        </h4>
        {trace.artifacts.length === 0 ? (
          <p style={detailText}>
            No artifacts are recorded in this trace
            {trace.provenance_status === 'complete'
              ? ''
              : '; the trace is not complete, so absence is not proof of absence'}
            .
          </p>
        ) : (
          <ul style={listStyle}>
            {trace.artifacts.map((artifact, index) => (
              <ArtifactRow key={artifact.artifact_id} index={index} artifact={artifact} />
            ))}
          </ul>
        )}
      </section>

      <p style={detailText}>
        {trace.links.length === 0
          ? 'No lineage links are recorded.'
          : `${trace.links.length} lineage link${trace.links.length === 1 ? '' : 's'} recorded between artifacts.`}
      </p>

      {trace.warnings.length > 0 ? (
        <section aria-label="Provenance warnings">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {trace.warnings.map((warning, index) => (
              <p key={index} style={{ ...detailText, color: 'var(--text-secondary)' }}>
                Warning: {warning}
              </p>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  )
}

/** The loaded impact content: the four-way classification and affected sets. */
function LoadedImpact({ impact }: { impact: ImpactAnalysis }) {
  const presentation = IMPACT_PRESENTATIONS[impact.impact_status]
  const affectedTotal =
    impact.affected_artifact_ids.length +
    impact.affected_trajectory_ids.length +
    impact.affected_policy_update_ids.length +
    impact.affected_checkpoint_ids.length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div
        style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', alignItems: 'center' }}
      >
        <StatusBadge
          label={presentation.label}
          tone={presentation.tone}
          glyph={presentation.glyph}
          note={presentation.note}
        />
      </div>

      {/* The contractual counter-claim, shown only for the unknown classification. */}
      {impact.impact_status === 'unknown_incomplete_lineage' && (
        <p style={detailText}>
          The recorded lineage is incomplete, so impact cannot be classified. This is an unknown
          result, not a statement that artifacts are unaffected.
        </p>
      )}
      {impact.impact_status === 'not_exposed_based_on_recorded_lineage' && (
        <p style={detailText}>
          Recorded lineage shows no exposure. This classification is limited to what the records
          show and does not prove that nothing outside the records was affected.
        </p>
      )}

      <p style={detailText}>
        {affectedTotal === 0
          ? 'No artifacts, trajectories, policy updates, or checkpoints are recorded as affected in this analysis.'
          : `Recorded as affected: ${impact.affected_artifact_ids.length} artifact${impact.affected_artifact_ids.length === 1 ? '' : 's'}, ${impact.affected_trajectory_ids.length} trajector${impact.affected_trajectory_ids.length === 1 ? 'y' : 'ies'}, ${impact.affected_policy_update_ids.length} policy update${impact.affected_policy_update_ids.length === 1 ? '' : 's'}, ${impact.affected_checkpoint_ids.length} checkpoint${impact.affected_checkpoint_ids.length === 1 ? '' : 's'}.`}
      </p>

      {impact.corruption_start_timestep !== null && (
        <p style={detailText}>
          Corruption window: timesteps {impact.corruption_start_timestep}
          {impact.corruption_end_timestep !== null
            ? `–${impact.corruption_end_timestep}`
            : ' onward'}
          .
        </p>
      )}

      {impact.warnings.length > 0 || impact.errors.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          {impact.warnings.map((warning, index) => (
            <p key={`w-${index}`} style={detailText}>
              Warning: {warning}
            </p>
          ))}
          {impact.errors.map((error, index) => (
            <p key={`e-${index}`} style={{ ...detailText, fontWeight: 600 }}>
              Analysis error: {error}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export interface ProvenanceViewProps {
  trace: PanelState<ProvenanceTrace>
  /** Incident impact state; omitted when no incident is focused. */
  impact?: PanelState<ImpactAnalysis>
  /** Retry affordance for the trace fetch (a safe GET). */
  onReloadTrace?: () => void
}

/**
 * Trace and impact panels together. The trace body renders from the run's
 * recorded provenance; the impact body renders from the incident's recorded
 * analysis, each independently loading / failed / loaded.
 */
export function ProvenanceView({ trace, impact, onReloadTrace }: ProvenanceViewProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <section aria-label="Provenance trace">
        {trace.state === 'loading' ? (
          <LoadingSkeleton rows={3} />
        ) : trace.state === 'error' ? (
          <ErrorState
            title="The provenance record could not be loaded"
            description={trace.error.message}
            action={
              onReloadTrace ? (
                <button
                  type="button"
                  onClick={onReloadTrace}
                  style={{
                    padding: '6px 14px',
                    background: 'var(--bg-input)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--text-primary)',
                    cursor: 'pointer',
                    fontFamily: 'var(--font-sans)',
                  }}
                >
                  Retry
                </button>
              ) : undefined
            }
          />
        ) : (
          <LoadedTrace trace={unwrapMockData(trace.data)} labeled={'label' in trace.data} />
        )}
      </section>

      {impact ? (
        <section aria-label="Incident impact">
          <h4
            style={{
              margin: '0 0 var(--space-2) 0',
              fontSize: 'var(--text-xs)',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            Incident impact analysis
          </h4>
          {impact.state === 'loading' ? (
            <LoadingSkeleton rows={2} />
          ) : impact.state === 'error' ? (
            <p role="status" style={detailText}>
              The impact analysis could not be loaded: {impact.error.message}
            </p>
          ) : (
            <LoadedImpact impact={unwrapMockData(impact.data)} />
          )}
        </section>
      ) : null}
    </div>
  )
}
