import { EmptyState } from '../../components/ui/EmptyState'
import type { AnomalyObservation } from '../../schemas/verification'

interface AnomalyFindingsPanelProps {
  anomalies: AnomalyObservation[]
  /** Present when the parent can navigate to an evidence detail view. */
  onOpenEvidence?: (evidenceRef: string) => void
}

/** Human-readable anomaly-type labels; the canonical value stays in the schema. */
const TYPE_LABELS: Record<AnomalyObservation['anomaly_type'], string> = {
  statistical: 'Statistical anomaly',
  distribution_shift: 'Distribution shift',
  reward_deviation: 'Reward deviation',
  observation_corruption: 'Observation corruption',
}

function scoreLine(anomaly: AnomalyObservation): string | null {
  if (anomaly.score === null && anomaly.threshold === null) return null
  if (anomaly.score === null) return `Trigger threshold ${anomaly.threshold}`
  if (anomaly.threshold === null) return `Detector score ${anomaly.score}`
  return `Detector score ${anomaly.score} (trigger threshold ${anomaly.threshold})`
}

/**
 * Detector outputs are findings, not verdicts. The panel always states that an
 * anomaly is a signal that still requires deterministic confirmation, so the
 * distinction between "detected statistically" and "contract violated" stays
 * visible even when a panel stacks both kinds of findings.
 */
export function AnomalyFindingsPanel({ anomalies, onOpenEvidence }: AnomalyFindingsPanelProps) {
  if (anomalies.length === 0) {
    return (
      <EmptyState
        title="No anomaly observations recorded"
        description="Anomaly detector signals for this incident scope appear here when the verification service records them. A signal is not a confirmed fault."
      />
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      {anomalies.map((anomaly) => {
        const score = scoreLine(anomaly)
        return (
          <article
            key={anomaly.anomaly_id ?? anomaly.description ?? anomaly.anomaly_type}
            aria-label={`Anomaly finding: ${anomaly.description ?? anomaly.anomaly_type}`}
            style={{
              border: '1px dashed var(--border-primary)',
              borderRadius: 'var(--radius-md)',
              padding: 'var(--space-3)',
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-2)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 'var(--space-3)' }}>
              <code style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-primary)' }}>
                {anomaly.anomaly_type}
              </code>
              <span
                style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-muted)',
                  fontFamily: 'var(--font-sans)',
                  whiteSpace: 'nowrap',
                }}
              >
                {TYPE_LABELS[anomaly.anomaly_type]}
              </span>
            </div>
            {anomaly.description && (
              <p style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                {anomaly.description}
              </p>
            )}
            {score && (
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                {score}
              </span>
            )}
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
              Detector signal — not a confirmed fault; deterministic checks remain authoritative.
            </span>
            {anomaly.evidence_refs.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
                {anomaly.evidence_refs.map((ref) =>
                  onOpenEvidence ? (
                    <button
                      key={ref}
                      type="button"
                      onClick={() => onOpenEvidence(ref)}
                      style={{
                        padding: '2px 8px',
                        background: 'transparent',
                        border: '1px solid var(--border-primary)',
                        borderRadius: 'var(--radius-sm)',
                        color: 'var(--text-primary)',
                        cursor: 'pointer',
                        fontFamily: 'var(--font-mono)',
                        fontSize: 'var(--text-xs)',
                      }}
                    >
                      {ref}
                    </button>
                  ) : (
                    <code
                      key={ref}
                      style={{
                        padding: '2px 8px',
                        fontFamily: 'var(--font-mono)',
                        fontSize: 'var(--text-xs)',
                        color: 'var(--text-secondary)',
                        border: '1px dashed var(--border-secondary)',
                        borderRadius: 'var(--radius-sm)',
                      }}
                    >
                      {ref}
                    </code>
                  ),
                )}
              </div>
            )}
          </article>
        )
      })}
    </div>
  )
}
