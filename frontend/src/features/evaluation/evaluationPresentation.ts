/**
 * Evaluation presentation — derived, deterministic.
 *
 * Pure functions translating the backend evaluation record into display rows.
 * Rules enforced:
 * - Aggregates are displayed from the record's own fields only; the frontend
 *   never recomputes acceptance or re-derives means from episode lists.
 * - A missing faulty baseline is "not supplied", never zero and never hidden.
 * - `success` claims exist only through `recovery_verified`; `inconclusive`
 *   stays inconclusive and `passed`/`failed` are the only other claims.
 * - Empty metric fields render as "Not available", which is the app's shared
 *   unknown-value presentation.
 */
import type { AcceptanceCriteria, Evaluation } from '../../schemas/evaluation'

export interface ComparisonSeriesInfo {
  /** The series the record supplies a baseline identity for. */
  hasBaseline: boolean
  hasRecovered: boolean
  /** False means "no faulty baseline was supplied with the record". */
  hasFaulty: boolean
}

export function comparisonSeries(record: Evaluation): ComparisonSeriesInfo {
  return {
    hasBaseline: record.baseline_run_id !== null,
    hasRecovered: record.recovered_run_id !== null,
    // Absence is a distinct display state the comparison must show.
    hasFaulty: 'faulty_runs' in record.comparison_results || hasFaultyAggregates(record),
  }
}

function hasFaultyAggregates(record: Evaluation): boolean {
  return record.evaluation_metrics['faulty_mean_reward'] !== undefined
}

/**
 * Criteria rows to display: only the criteria the record actually configured.
 * Unconfigured criteria are not rendered as zeros.
 */
export interface CriteriaRow {
  key: string
  label: string
  value: string
}

const CRITERIA_LABELS: ReadonlyArray<{ key: keyof AcceptanceCriteria; label: string }> = [
  { key: 'minimum_recovered_success_rate', label: 'Minimum recovered success rate' },
  {
    key: 'minimum_success_rate_improvement_vs_faulty',
    label: 'Minimum success-rate improvement vs faulty',
  },
  {
    key: 'maximum_success_rate_regression_vs_healthy',
    label: 'Maximum success-rate regression vs healthy',
  },
  {
    key: 'minimum_mean_reward_improvement_vs_faulty',
    label: 'Minimum mean-reward improvement vs faulty',
  },
  {
    key: 'maximum_mean_reward_regression_vs_healthy',
    label: 'Maximum mean-reward regression vs healthy',
  },
  { key: 'maximum_collision_rate', label: 'Maximum collision rate' },
  { key: 'maximum_timeout_rate', label: 'Maximum timeout rate' },
  { key: 'minimum_valid_episodes_per_group', label: 'Minimum valid episodes per group' },
  { key: 'require_no_episode_errors', label: 'No episode errors required' },
]

export function criteriaRows(record: Evaluation): CriteriaRow[] {
  const configured = record.acceptance_criteria
  const rows: CriteriaRow[] = []
  for (const { key, label } of CRITERIA_LABELS) {
    const raw = configured[key]
    if (raw === undefined || raw === null) continue
    rows.push({
      key,
      label,
      value: typeof raw === 'boolean' ? (raw ? 'Required' : 'Not required') : String(raw),
    })
  }
  return rows
}

export interface OutcomeClaim {
  label: string
  tone: 'neutral' | 'strong' | 'quiet'
  /** `passed` / `failed` / `inconclusive` come verbatim from the record. */
  outcome: 'passed' | 'failed' | 'inconclusive' | 'not_run' | 'blocked'
  /** Backend-established recovery claim, shown only when the record states it. */
  recovery_verified: boolean
}

export function outcomeClaim(record: Evaluation): OutcomeClaim {
  const outcome = record.evaluation_status
  const labels: Record<OutcomeClaim['outcome'], { label: string; tone: OutcomeClaim['tone'] }> = {
    passed: { label: 'Evaluation passed the configured acceptance criteria', tone: 'strong' },
    failed: { label: 'Evaluation did not meet the configured acceptance criteria', tone: 'strong' },
    inconclusive: {
      label: 'Evaluation inconclusive — results were weak or mixed',
      tone: 'neutral',
    },
    not_run: { label: 'Evaluation has not been run', tone: 'quiet' },
    blocked: { label: 'Evaluation blocked', tone: 'quiet' },
  }
  const presentation = labels[outcome]
  return {
    label: presentation.label,
    tone: presentation.tone,
    outcome,
    recovery_verified: record.recovery_verified,
  }
}

/**
 * Comparison rows in display order. When the record supplies a mean for a
 * series, the value shows; when it does not, the row reports "Not available"
 * instead of a zero — a missing measurement is not a measured zero.
 */
export interface ComparisonRow {
  key: string
  series: string
  columns: { reward: string; success: string; length: string }
}

export function comparisonRows(record: Evaluation): ComparisonRow[] {
  return [
    {
      key: 'recovered',
      series: 'Recovered',
      columns: {
        reward: meanLabel(record.recovered_mean_reward),
        success: rateLabel(record.recovered_success_rate),
        length: lengthLabel(record.recovered_episode_length),
      },
    },
    {
      key: 'baseline',
      series: 'Healthy baseline',
      columns: {
        reward: meanLabel(record.baseline_mean_reward),
        success: rateLabel(record.baseline_success_rate),
        length: lengthLabel(record.baseline_episode_length),
      },
    },
    {
      key: 'faulty',
      series: 'Faulty baseline',
      columns: hasFaultyAggregates(record)
        ? {
            reward: String(record.evaluation_metrics['faulty_mean_reward']),
            success: String(record.evaluation_metrics['faulty_success_rate'] ?? 'Not available'),
            length: String(record.evaluation_metrics['faulty_episode_length'] ?? 'Not available'),
          }
        : { reward: 'Not supplied', success: 'Not supplied', length: 'Not supplied' },
    },
  ]
}

/**
 * Deltas come verbatim from the record. A null delta is honestly reported as
 * "Not computed" — never inferred from the two means the record shows.
 */
export function improvementRows(record: Evaluation): ComparisonRow[] {
  return [
    {
      key: 'reward_improvement',
      series: 'Mean reward improvement (recovered vs healthy)',
      columns: { reward: improvementLabel(record.reward_improvement), success: '', length: '' },
    },
    {
      key: 'success_improvement',
      series: 'Success-rate improvement (recovered vs healthy)',
      columns: {
        reward: improvementLabel(record.success_rate_improvement),
        success: '',
        length: '',
      },
    },
  ]
}

function meanLabel(value: number | null): string {
  return value === null ? 'Not available' : value.toFixed(2)
}

function rateLabel(value: number | null): string {
  return value === null ? 'Not available' : `${(value * 100).toFixed(1)}%`
}

function lengthLabel(value: number | null): string {
  return value === null ? 'Not available' : String(Math.round(value))
}

function improvementLabel(value: number | null): string {
  // The backend may legitimately record a signed direction of improvement.
  return value === null ? 'Not computed' : (value > 0 ? '+' : '') + value.toFixed(4)
}
