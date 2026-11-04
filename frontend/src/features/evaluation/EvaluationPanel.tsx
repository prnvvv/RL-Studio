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

/** Dashboard-only metric cards. Every value is the record's own; nothing is computed here. */
function MetricCards({
  evaluation,
  rows,
  improvements,
}: {
  evaluation: Evaluation
  rows: ReturnType<typeof comparisonRows>
  improvements: ReturnType<typeof improvementRows>
}) {
  const series = rows.filter((row) => row.key !== 'faulty' || row.columns.reward !== 'Not supplied')
  const isMissing = (value: string) =>
    ['Not available', 'Not supplied', 'Not computed'].includes(value)
  return (
    <div className="rp-metrics" aria-label="Evaluation metrics" role="group">
      {series.map((row) => (
        <article className="rp-metric" key={row.key} aria-label={`${row.series} metrics`}>
          <h4 className="rp-metric__title">{row.series}</h4>
          <span
            className={`rp-metric__value${isMissing(row.columns.reward) ? ' rp-metric__value--na' : ''}`}
          >
            {row.columns.reward}
          </span>
          <dl className="rp-metric__rows">
            <div className="rp-metric__row">
              <dt>Success rate</dt>
              <dd>{row.columns.success}</dd>
            </div>
            <div className="rp-metric__row">
              <dt>Episode length</dt>
              <dd>{row.columns.length}</dd>
            </div>
          </dl>
        </article>
      ))}
      {improvements.map((row) => (
        <article className="rp-metric" key={row.key} aria-label={row.series}>
          <h4 className="rp-metric__title">{row.series}</h4>
          <span
            className={`rp-metric__value${isMissing(row.columns.reward) ? ' rp-metric__value--na' : ''}`}
          >
            {row.columns.reward}
          </span>
        </article>
      ))}
      <article className="rp-metric" aria-label="Evaluation scope">
        <h4 className="rp-metric__title">Evaluation scope</h4>
        <dl className="rp-metric__rows">
          <div className="rp-metric__row">
            <dt>Episodes</dt>
            <dd>{evaluation.episode_count === null ? 'Not recorded' : evaluation.episode_count}</dd>
          </div>
          <div className="rp-metric__row">
            <dt>Seeds</dt>
            <dd>{evaluation.seeds.length > 0 ? evaluation.seeds.join(', ') : 'None recorded'}</dd>
          </div>
        </dl>
      </article>
    </div>
  )
}

/** The loaded record: outcome, comparison, improvements, criteria, context. */
function LoadedEvaluation({
  evaluation,
  dashboard = false,
}: {
  evaluation: Evaluation
  dashboard?: boolean
}) {
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

  // Default presentation (used by Diagnosis) keeps its inline styles; the Reports dashboard uses classes.
  const titleProps = dashboard
    ? { className: 'rp-eval__section-title' }
    : {
        style: {
          margin: '0 0 var(--space-2) 0',
          fontSize: 'var(--text-xs)',
          fontWeight: 600,
          textTransform: 'uppercase' as const,
          letterSpacing: '0.06em',
          color: 'var(--text-secondary)',
          fontFamily: 'var(--font-sans)',
        },
      }
  const detailProps = dashboard ? { className: 'rp-eval__detail' } : { style: detailText }
  const cell = (extra?: Record<string, unknown>) =>
    dashboard ? {} : { style: { ...tableCell, ...extra } }

  return (
    <div
      className={dashboard ? 'rp-eval' : undefined}
      style={
        dashboard ? undefined : { display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }
      }
    >
      <div
        className={dashboard ? 'rp-eval__badges' : undefined}
        style={
          dashboard
            ? undefined
            : { display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', alignItems: 'center' }
        }
      >
        <StatusBadge label={claim.label} tone={claim.tone} glyph={glyphFor(claim.outcome)} />
        <StatusBadge
          label={verifiedBadge.label}
          tone={verifiedBadge.tone}
          glyph={verifiedBadge.glyph}
        />
      </div>

      {dashboard ? (
        <MetricCards evaluation={evaluation} rows={rows} improvements={improvements} />
      ) : null}

      <section aria-label="Baseline comparison">
        <h4 {...titleProps}>Baseline comparison</h4>
        <table
          className={dashboard ? 'rp-eval__table' : undefined}
          style={dashboard ? undefined : { width: '100%', borderCollapse: 'collapse' }}
        >
          <caption className="visually-hidden">
            Baseline comparison of recovered, healthy, and faulty series
          </caption>
          <thead>
            <tr>
              <th scope="col" {...cell({ fontWeight: 600 })}>
                Series
              </th>
              <th scope="col" {...cell({ fontWeight: 600 })}>
                Mean reward
              </th>
              <th scope="col" {...cell({ fontWeight: 600 })}>
                Success rate
              </th>
              <th scope="col" {...cell({ fontWeight: 600 })}>
                Episode length
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <th scope="row" {...cell({ fontWeight: 500, color: 'var(--text-primary)' })}>
                  {row.series}
                </th>
                <td {...cell()}>{row.columns.reward}</td>
                <td {...cell()}>{row.columns.success}</td>
                <td {...cell()}>{row.columns.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p
          {...detailProps}
          style={
            dashboard
              ? { marginTop: 'var(--space-2)' }
              : { ...detailText, marginTop: 'var(--space-2)' }
          }
        >
          The comparison shows only what the record supplies. A missing faulty baseline is “Not
          supplied”, a missing measurement is “Not available”, and a missing delta is “Not computed
          by the backend”.
        </p>
      </section>

      <section aria-label="Recorded improvements">
        <h4 {...titleProps}>Recorded improvements</h4>
        {improvements.map((row) => (
          <p key={row.key} {...detailProps}>
            {row.series}: {row.columns.reward}
          </p>
        ))}
      </section>

      <section aria-label="Acceptance criteria">
        <h4 {...titleProps}>Configured acceptance criteria ({criteria.length})</h4>
        {criteria.length === 0 ? (
          <p {...detailProps}>
            The record carries no configured acceptance criteria. They were not inferred after the
            results were seen.
          </p>
        ) : (
          <ul
            className={dashboard ? 'rp-eval__list' : undefined}
            style={dashboard ? undefined : { listStyle: 'none', margin: 0, padding: 0 }}
          >
            {criteria.map((criterion) => (
              <li
                key={criterion.key}
                {...(dashboard ? {} : { style: { ...detailText, padding: '2px 0' } })}
              >
                {criterion.label}: {criterion.value}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Evaluation context">
        <p {...detailProps}>
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
            <p key={`w-${index}`} {...detailProps}>
              Warning: {warning}
            </p>
          ))}
          {evaluation.errors.map((error, index) => (
            <p key={`e-${index}`} {...detailProps} style={{ fontWeight: 600 }}>
              Evaluation error: {error}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  )
}

export interface EvaluationPanelProps {
  /** `dashboard` adds metric cards and the Reports styling; the default is unchanged. */
  presentation?: 'default' | 'dashboard'
  evaluation?: PanelState<Evaluation>
  /** Retry affordance for loading the record (a safe GET). */
  onReload?: () => void
}

export function EvaluationPanel({
  evaluation,
  onReload,
  presentation = 'default',
}: EvaluationPanelProps) {
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
        <LoadedEvaluation
          evaluation={unwrapMockData(evaluation.data)}
          dashboard={presentation === 'dashboard'}
        />
      )}
    </section>
  )
}
