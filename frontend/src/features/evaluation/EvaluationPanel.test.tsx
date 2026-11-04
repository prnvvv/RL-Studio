import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Evaluation } from '../../schemas/evaluation'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'
import type { MockData } from '../../mocks'
import { EvaluationPanel } from './EvaluationPanel'

const CREATED = '2026-11-02T00:03:00Z'

function evaluation(overrides: Partial<Evaluation> = {}): Evaluation {
  return {
    evaluation_id: 'eval_1',
    incident_id: 'inc_demo',
    recovery_id: 'rec_1',
    baseline_run_id: 'run_healthy',
    recovered_run_id: 'run_recovered',
    evaluation_status: 'passed',
    evaluation_environment_version: 'warehouse_v1',
    baseline_mean_reward: 95.5,
    recovered_mean_reward: 94.25,
    baseline_success_rate: 0.9,
    recovered_success_rate: 0.852,
    baseline_episode_length: 820.4,
    recovered_episode_length: 831.6,
    reward_improvement: -1.25,
    success_rate_improvement: null,
    evaluation_metrics: {},
    comparison_results: {},
    acceptance_criteria: { minimum_recovered_success_rate: 0.8, require_no_episode_errors: true },
    recovery_verification_status: 'passed',
    recovery_verified: true,
    episode_count: 20,
    seeds: [0, 1, 2],
    evidence_ids: [],
    warnings: [],
    errors: [],
    details: {},
    created_at: CREATED,
    completed_at: CREATED,
    ...overrides,
  }
}

type PanelState<E> = ServiceQueryState<E | MockData<E>>

function ok<E>(data: E): PanelState<E> {
  return { state: 'ok', data }
}

function loading<E>(): PanelState<E> {
  return { state: 'loading' }
}

function errorState<E>(): PanelState<E> {
  return {
    state: 'error',
    error: { kind: 'network', message: 'The studio service is unreachable right now.' },
    data: null,
  }
}

describe('EvaluationPanel — record states', () => {
  it('renders an explanatory note with no success claim when no record is supplied', () => {
    render(<EvaluationPanel />)
    expect(
      screen.getByText(/No evaluation record is supplied for this incident yet/),
    ).toBeInTheDocument()
    expect(screen.queryByText(/Recovery verified/)).not.toBeInTheDocument()
  })

  it('renders a skeleton while loading and an error with retry when the fetch fails', () => {
    const onReload = vi.fn()
    const { rerender } = render(<EvaluationPanel evaluation={loading<Evaluation>()} />)
    expect(screen.queryByText(/Baseline comparison/)).not.toBeInTheDocument()

    rerender(<EvaluationPanel evaluation={errorState<Evaluation>()} onReload={onReload} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onReload).toHaveBeenCalledTimes(1)
  })
})

describe('EvaluationPanel — loaded record', () => {
  it('shows the backend verdict verbatim with the verified badge', () => {
    render(<EvaluationPanel evaluation={ok(evaluation())} />)
    expect(screen.getByText('Recovery verified by evaluation')).toBeInTheDocument()
    expect(
      screen.getByText(/Evaluation passed the configured acceptance criteria/),
    ).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Baseline comparison' })).toBeInTheDocument()
  })

  it('renders the comparison rows from the record only, including the missing faulty series', () => {
    render(<EvaluationPanel evaluation={ok(evaluation())} />)
    // Supplied aggregates shown; faulty baseline not zero-filled.
    expect(screen.getByText('94.25')).toBeInTheDocument()
    expect(screen.getByText('85.2%')).toBeInTheDocument()
    expect(screen.getAllByText('Not supplied').length).toBe(3)
    expect(screen.getAllByText('Not supplied')[0]!.closest('tr')).toHaveTextContent(
      'Faulty baseline',
    )
  })

  it('uses "Not available" for missing measurements, never a zero', () => {
    const record = evaluation({
      baseline_mean_reward: null,
      baseline_success_rate: null,
      baseline_episode_length: null,
    })
    render(<EvaluationPanel evaluation={ok(record)} />)
    expect(screen.getAllByText('Not available').length).toBe(3)
  })

  it('reports recorded deltas verbatim and missing deltas as not computed', () => {
    render(<EvaluationPanel evaluation={ok(evaluation())} />)
    expect(
      screen.getByText(/Mean reward improvement \(recovered vs healthy\): -1\.2500/),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Success-rate improvement \(recovered vs healthy\): Not computed/),
    ).toBeInTheDocument()
  })

  it('shows only the configured criteria', () => {
    render(<EvaluationPanel evaluation={ok(evaluation())} />)
    expect(screen.getByText('Configured acceptance criteria (2)')).toBeInTheDocument()
    expect(screen.getByText(/Minimum recovered success rate: 0\.8/)).toBeInTheDocument()
    expect(screen.getByText(/No episode errors required: Required/)).toBeInTheDocument()
  })

  it('stays inconclusive and without a verified claim when the record says so', () => {
    const record = evaluation({
      evaluation_status: 'inconclusive',
      recovery_verification_status: 'inconclusive',
      recovery_verified: false,
    })
    render(<EvaluationPanel evaluation={ok(record)} />)
    expect(screen.getByText(/Evaluation inconclusive/)).toBeInTheDocument()
    expect(screen.getByText('Recovery not verified by evaluation')).toBeInTheDocument()
    expect(screen.queryByText('Recovery verified by evaluation')).not.toBeInTheDocument()
  })

  it('never shows a verified badge when the record did not verify recovery', () => {
    const record = evaluation({ evaluation_status: 'failed', recovery_verified: false })
    render(<EvaluationPanel evaluation={ok(record)} />)
    expect(screen.getByText(/did not meet the configured acceptance criteria/)).toBeInTheDocument()
    expect(screen.getByText('Recovery not verified by evaluation')).toBeInTheDocument()
  })

  it('renders context and warnings verbatim from the record', () => {
    const record = evaluation({
      episode_count: null,
      seeds: [],
      warnings: ['Recovered episodes had one timeout each.'],
      baseline_run_id: null,
    })
    render(<EvaluationPanel evaluation={ok(record)} />)
    expect(screen.getByText(/Episode count: not recorded/)).toBeInTheDocument()
    expect(screen.getByText(/Seeds: none recorded/)).toBeInTheDocument()
    expect(screen.getByText(/Warning: Recovered episodes had one timeout/)).toBeInTheDocument()
  })
})

describe('EvaluationPanel dashboard presentation', () => {
  it('adds metric cards built only from the record, and leaves the default presentation unchanged', () => {
    const { unmount } = render(
      <EvaluationPanel evaluation={ok(evaluation())} presentation="dashboard" />,
    )
    const group = screen.getByRole('group', { name: 'Evaluation metrics' })
    const recovered = within(group).getByRole('article', { name: 'Recovered metrics' })
    expect(recovered).toHaveTextContent('94.25')
    expect(recovered).toHaveTextContent('85.2%')
    expect(
      within(group).getByRole('article', { name: 'Healthy baseline metrics' }),
    ).toHaveTextContent('95.50')
    expect(within(group).getByRole('article', { name: 'Evaluation scope' })).toHaveTextContent('20')
    // a delta the record does not supply is "Not computed", never derived from the two means shown
    expect(
      within(group).getByRole('article', { name: /Success-rate improvement/ }),
    ).toHaveTextContent('Not computed')
    expect(
      within(group).getByRole('article', { name: /Mean reward improvement/ }),
    ).toHaveTextContent('-1.2500')
    // no faulty baseline was supplied, so no faulty card is drawn
    expect(
      within(group).queryByRole('article', { name: 'Faulty baseline metrics' }),
    ).not.toBeInTheDocument()
    // the existing sections are all still present
    expect(screen.getByRole('region', { name: 'Baseline comparison' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Acceptance criteria' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Evaluation context' })).toBeInTheDocument()
    expect(screen.getByText('Recovery verified by evaluation')).toBeInTheDocument()
    unmount()

    render(<EvaluationPanel evaluation={ok(evaluation())} />)
    expect(screen.queryByRole('group', { name: 'Evaluation metrics' })).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Baseline comparison' })).toBeInTheDocument()
  })

  it('shows missing measurements as Not available, never as zero', () => {
    render(
      <EvaluationPanel
        evaluation={ok(
          evaluation({
            recovered_mean_reward: null,
            recovered_success_rate: null,
            episode_count: null,
            seeds: [],
          }),
        )}
        presentation="dashboard"
      />,
    )
    const recovered = screen.getByRole('article', { name: 'Recovered metrics' })
    expect(recovered).toHaveTextContent('Not available')
    expect(recovered).not.toHaveTextContent('0.00')
    expect(screen.getByRole('article', { name: 'Evaluation scope' })).toHaveTextContent(
      'Not recorded',
    )
  })

  it('keeps loading and error states in the dashboard presentation', () => {
    const { rerender } = render(<EvaluationPanel evaluation={loading()} presentation="dashboard" />)
    expect(screen.queryByRole('group', { name: 'Evaluation metrics' })).not.toBeInTheDocument()
    rerender(
      <EvaluationPanel evaluation={errorState()} onReload={vi.fn()} presentation="dashboard" />,
    )
    expect(screen.getByText('The evaluation record could not be loaded')).toBeInTheDocument()
  })
})
