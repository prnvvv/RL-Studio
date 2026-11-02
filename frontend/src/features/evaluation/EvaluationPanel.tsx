/**
 * Evaluation panel (Person 4) — displays a recorded evaluation verbatim.
 *
 * All row derivations come from `evaluationPresentation`; the component itself
 * adds no metric, threshold, or verdict. The recovery-verified claim is shown
 * strictly from the backend's `recovery_verified` field — the frontend never
 * computes acceptance or strengthens an inconclusive result.
 *
 * Missing-baseline presentation rules (frontend/AGENTS.md §14.4):
 * - A faulty series the record does not supply reads "Not supplied", never 0.
 * - A missing measurement reads "Not available", never 0.
 * - A null delta reads "Not computed" — never re-derived from shown means.
 */
import { StatusBadge } from '../../components/ui/StatusBadge'
import { ErrorState } from '../../components/ui/ErrorState'
import { LoadingSkeleton } from '../../components/ui/LoadingSkeleton'
import { unwrapMockData, type MockData } from '../../mocks'
import type { Evaluation } from '../../schemas/evaluation'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'
import {
  comparisonRows,
  criteriaRows,
  improvementRows,
  outcomeClaim,
} from './evaluationPresentation'

type PanelState<E> = ServiceQueryState<E | MockData<E>>

const detailText = {
  margin: 0,
  fontSize: 'var(--text-xs)',
  color: 'var(--text-secondary)',
  fontFamily: 'var(--font-sans)',
  lineHeight: 1.6,
} as const

const tableCell = {
  padding: 'var(--space-2) var(--space-3)',
  fontSize: 'var(--text-xs)',
  fontFamily: 'var(--font-sans)',
  textAlign: 'left' as const,
  borderBottom: '1px solid var(--border-secondary)',
} as const

function glyphFor(status: Evaluation['evaluation_status']): 'check' | 'cross' | 'query' | 'dot' {
  switch (status) {
    case 'passed':
      return 'check'
    case 'failed':
      return 'cross'
    case 'inconclusive':
      return 'query'
    default:
      return 'dot'
  }
}

/** The loaded record: outcome, comparison, improvements, criteria, context. */
function LoadedEvaluation({ evaluation }: { evaluation: Evaluation }) {
  const claim = outcomeClaim(evaluation)
  const rows = comparisonRows(evaluation)
  const improvements = improvementRows(evaluation)
  const criteria = criteriaRows(evaluation)
  // The verified claim exists only where the record states it.
  const verifiedBadge = evaluation.recovery_verified
    ? { label: 'Recovery verified by evaluation', tone: 'strong' as const, glyph: 'check' as const }
    : {
        label: 'Recovery not verified by evaluation',
        tone: 'quiet' as const,
        glyph: 'query' as const,
      }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div
        style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', alignItems: 'center' }}
      >
        <StatusBadge label={claim.label} tone={claim.tone} glyph={glyphFor(claim.outcome)} />
        <StatusBadge
          label={verifiedBadge.label}
          tone={verifiedBadge.tone}
          glyph={verifiedBadge.glyph}
        />
      </div>

      <section aria-label="Baseline comparison">
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
          Baseline comparison
        </h4>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <caption className="visually-hidden">
            Baseline comparison of recovered, healthy, and faulty series
          </caption>
          <thead>
            <tr>
              <th scope="col" style={{ ...tableCell, fontWeight: 600 }}>
                Series
              </th>
              <th scope="col" style={{ ...tableCell, fontWeight: 600 }}>
                Mean reward
              </th>
              <th scope="col" style={{ ...tableCell, fontWeight: 600 }}>
                Success rate
              </th>
              <th scope="col" style={{ ...tableCell, fontWeight: 600 }}>
                Episode length
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <th
                  scope="row"
                  style={{ ...tableCell, fontWeight: 500, color: 'var(--text-primary)' }}
                >
                  {row.series}
                </th>
                <td style={tableCell}>{row.columns.reward}</td>
                <td style={tableCell}>{row.columns.success}</td>
                <td style={tableCell}>{row.columns.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p style={{ ...detailText, marginTop: 'var(--space-2)' }}>
          The comparison shows only what the record supplies. A missing faulty baseline is “Not
          supplied”, a missing measurement is “Not available”, and a missing delta is “Not computed
          by the backend”.
        </p>
      </section>

      <section aria-label="Recorded improvements">
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
          Recorded improvements
        </h4>
        {improvements.map((row) => (
          <p key={row.key} style={detailText}>
            {row.series}: {row.columns.reward}
          </p>
        ))}
      </section>

      <section aria-label="Acceptance criteria">
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
          Configured acceptance criteria ({criteria.length})
        </h4>
        {criteria.length === 0 ? (
          <p style={detailText}>
            The record carries no configured acceptance criteria. They were not inferred after the
            results were seen.
          </p>
        ) : (
          <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
            {criteria.map((criterion) => (
              <li key={criterion.key} style={{ ...detailText, padding: '2px 0' }}>
                {criterion.label}: {criterion.value}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Evaluation context">
        <p style={detailText}>
          {evaluation.episode_count === null
            ? 'Episode count: not recorded.'
            : `Episodes evaluated: ${evaluation.episode_count}.`}
          {evaluation.evaluation_environment_version
            ? ` Evaluation environment: ${evaluation.evaluation_environment_version}.`
            : ' Evaluation environment: not recorded.'}
          {evaluation.baseline_run_id
            ? ` Healthy baseline run: ${evaluation.baseline_run_id}.`
            : ''}
          {evaluation.recovered_run_id ? ` Recovered run: ${evaluation.recovered_run_id}.` : ''}
          {evaluation.seeds.length > 0
            ? ` Seeds: ${evaluation.seeds.join(', ')}.`
            : ' Seeds: none recorded.'}
        </p>
      </section>

      {evaluation.warnings.length > 0 || evaluation.errors.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          {evaluation.warnings.map((warning, index) => (
            <p key={`w-${index}`} style={detailText}>
              Warning: {warning}
            </p>
          ))}
          {evaluation.errors.map((error, index) => (
            <p key={`e-${index}`} style={{ ...detailText, fontWeight: 600 }}>
              Evaluation error: {error}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export interface EvaluationPanelProps {
  evaluation?: PanelState<Evaluation>
  /** Retry affordance for loading the record (a safe GET). */
  onReload?: () => void
}

export function EvaluationPanel({ evaluation, onReload }: EvaluationPanelProps) {
  return (
    <section aria-label="Evaluation record">
      {!evaluation ? (
        <p style={detailText}>
          No evaluation record is supplied for this incident yet. An evaluation runs only against
          the recorded recovery and baseline identities; without it, recovery success is not
          established.
        </p>
      ) : evaluation.state === 'loading' ? (
        <LoadingSkeleton rows={3} />
      ) : evaluation.state === 'error' ? (
        <ErrorState
          title="The evaluation record could not be loaded"
          description={evaluation.error.message}
          action={
            onReload ? (
              <button
                type="button"
                onClick={onReload}
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
        <LoadedEvaluation evaluation={unwrapMockData(evaluation.data)} />
      )}
    </section>
  )
}
