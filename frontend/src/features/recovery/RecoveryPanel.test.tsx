import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Recovery, RecoveryAssessment } from '../../schemas/recovery'
import type { RecoveryService } from '../../services/recovery'
import type { ServiceResult } from '../../services/types'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'
import { RecoveryPanel } from './RecoveryPanel'

const CREATED = '2026-11-02T00:00:00Z'

function check(name: string, outcome: RecoveryAssessment['compatibility'][number]['outcome']) {
  return { name, outcome, detail: 'recorded detail', evidence_ids: [] }
}

export function assessment(overrides: Partial<RecoveryAssessment> = {}): RecoveryAssessment {
  return {
    recovery_assessment_id: 'assess_1',
    incident_id: 'inc_demo',
    recovery_eligibility: 'eligible',
    recovery_strategy: 'restore_checkpoint',
    recovery_reason: null,
    source_checkpoint_id: 'ckpt_pre_impact',
    target_environment_version: 'warehouse_v1',
    target_agent_config_fingerprint: null,
    compatibility: [check('checkpoint exists', 'pass'), check('environment compatible', 'pass')],
    lineage_gaps: [],
    evidence_ids: [],
    warnings: [],
    errors: [],
    details: {},
    created_at: CREATED,
    ...overrides,
  }
}

export function recovery(overrides: Partial<Recovery> = {}): Recovery {
  return {
    recovery_id: 'rec_1',
    incident_id: 'inc_demo',
    assessment_id: 'assess_1',
    recovery_status: 'completed',
    recovery_strategy: 'restore_checkpoint',
    recovery_reason: null,
    source_checkpoint_id: 'ckpt_pre_impact',
    recovery_artifact_id: null,
    recovered_checkpoint_id: 'ckpt_recovered',
    target_environment_version: 'warehouse_v1',
    target_agent_config_fingerprint: null,
    recovery_started_at: '2026-11-02T00:01:00Z',
    recovery_completed_at: '2026-11-02T00:02:00Z',
    proposed_actions: [
      {
        action: 'restore_checkpoint',
        status: 'proposed',
        detail: null,
        started_at: null,
        completed_at: null,
      },
    ],
    executed_actions: [
      {
        action: 'restore_checkpoint',
        status: 'completed',
        detail: null,
        started_at: null,
        completed_at: null,
      },
    ],
    preflight: {},
    failure_reason: null,
    evidence_ids: [],
    warnings: [],
    errors: [],
    details: {},
    created_at: CREATED,
    updated_at: '2026-11-02T00:02:00Z',
    ...overrides,
  }
}

import type { MockData } from '../../mocks'

type PanelState<T> = ServiceQueryState<T | MockData<T>>

function ok<T>(data: T): PanelState<T> {
  return { state: 'ok', data }
}

function loading<T>(): PanelState<T> {
  return { state: 'loading' }
}

function errorState<T>(kind: 'network' | 'conflict' = 'network'): PanelState<T> {
  return {
    state: 'error',
    error:
      kind === 'conflict'
        ? {
            kind: 'conflict',
            status: 409,
            message: 'The recorded state does not allow this request.',
          }
        : { kind: 'network', message: 'The studio service is unreachable right now.' },
    data: null,
  }
}

/** Fake service capturing the createRecovery payload. */
function fakeService(
  createResult: ServiceResult<Recovery> = { state: 'ok', data: recovery() },
): RecoveryService {
  return {
    createAssessment: vi.fn(async () => {
      throw new Error('not used in this test')
    }),
    getAssessment: vi.fn(async () => {
      throw new Error('not used in this test')
    }),
    createRecovery: vi.fn(async () => createResult),
    getRecovery: vi.fn(async () => {
      throw new Error('not used in this test')
    }),
  }
}

const baseProps = {
  incidentId: 'inc_demo',
  service: undefined as unknown as RecoveryService,
}

describe('RecoveryPanel — assessment states', () => {
  it('renders an explanatory note with no actionable control when no assessment is supplied', () => {
    render(<RecoveryPanel {...baseProps} />)
    expect(screen.getByText(/No assessment is supplied for this incident yet/)).toBeInTheDocument()
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('renders a skeleton while the assessment loads', () => {
    render(<RecoveryPanel {...baseProps} assessment={loading<RecoveryAssessment>()} />)
    expect(screen.queryByText(/Eligibility:/)).not.toBeInTheDocument()
  })

  it('renders an honest error with a safe retry', () => {
    const onReloadAssessment = vi.fn()
    render(
      <RecoveryPanel
        {...baseProps}
        assessment={errorState<RecoveryAssessment>()}
        onReloadAssessment={onReloadAssessment}
      />,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onReloadAssessment).toHaveBeenCalledTimes(1)
  })
})

describe('RecoveryPanel — gating', () => {
  it('shows the recorded check outcomes verbatim and opens the gate for an eligible, all-pass assessment', () => {
    render(<RecoveryPanel {...baseProps} assessment={ok(assessment())} />)
    expect(screen.getByText('Eligibility: eligible')).toBeInTheDocument()
    expect(screen.getAllByText('Check: pass')).toHaveLength(2)
    expect(screen.getByText('Recorded compatibility checks (2)')).toBeInTheDocument()
    expect(
      screen.getByText(/The recorded assessment is eligible with all compatibility checks passed/),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Request controlled recovery' })).toBeInTheDocument()
  })

  it('offers no actionable control at all when a check did not pass', () => {
    render(
      <RecoveryPanel
        {...baseProps}
        assessment={ok(assessment({ compatibility: [check('hash integrity', 'fail')] }))}
      />,
    )
    expect(
      screen.getAllByText(/hash integrity: fail|A recorded compatibility check did not pass/)
        .length,
    ).toBeGreaterThan(0)
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('does not open the gate for non-passing outcomes like unknown or skipped', () => {
    render(
      <RecoveryPanel
        {...baseProps}
        assessment={ok(assessment({ compatibility: [check('lineage verified', 'skipped')] }))}
      />,
    )
    expect(screen.getByText('Check: skipped')).toBeInTheDocument()
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('treats an empty compatibility list as a closed gate with an explicit explanation', () => {
    render(<RecoveryPanel {...baseProps} assessment={ok(assessment({ compatibility: [] }))} />)
    expect(screen.getAllByText(/records no compatibility checks/).length).toBeGreaterThan(0)
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })

  it('does not open the gate for ineligible eligibility', () => {
    render(
      <RecoveryPanel
        {...baseProps}
        assessment={ok(assessment({ recovery_eligibility: 'unknown' }))}
      />,
    )
    expect(screen.getByText('Eligibility: unknown')).toBeInTheDocument()
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })
})

describe('RecoveryPanel — confirmation-gated execution request', () => {
  it('sends the execution request only after explicit confirmation', async () => {
    const record = recovery()
    const service = fakeService({ state: 'ok', data: record })
    const onRequested = vi.fn()
    render(
      <RecoveryPanel
        {...baseProps}
        service={service}
        assessment={ok(assessment())}
        onRequested={onRequested}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Request controlled recovery' }))
    // Dialog content first: the action, the incident, and the checkpoint.
    expect(
      screen.getByText(/will ask the backend to execute a controlled recovery/),
    ).toBeInTheDocument()
    expect(screen.getByText(/Send execution request/)).toBeInTheDocument()

    const createRecovery = service.createRecovery as ReturnType<typeof vi.fn>
    expect(createRecovery).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Send execution request' }))

    await waitFor(() => expect(createRecovery).toHaveBeenCalledTimes(1))
    const [incidentId, request] = createRecovery.mock.calls[0] as [string, Record<string, unknown>]
    expect(incidentId).toBe('inc_demo')
    expect(request['assessment_id']).toBe('assess_1')
    expect(request['execute']).toBe(true)
    expect((request['approval'] as Record<string, unknown>)['approved']).toBe(true)
    expect(typeof request['idempotency_key']).toBe('string')

    await waitFor(() => expect(onRequested).toHaveBeenCalledTimes(1))
    // The page receives the created record so it can track execution state.
    expect(onRequested).toHaveBeenCalledWith(record)
    // The dialog closes after the confirmed request completes.
    expect(screen.queryByRole('button', { name: 'Send execution request' })).not.toBeInTheDocument()
  })

  it('surfaces a request failure instead of retrying or claiming success', async () => {
    const service = fakeService({
      state: 'error',
      error: {
        kind: 'conflict',
        status: 409,
        message: 'The recorded state does not allow this request.',
      },
    })
    const onRequested = vi.fn()
    render(
      <RecoveryPanel
        {...baseProps}
        service={service}
        assessment={ok(assessment())}
        onRequested={onRequested}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Request controlled recovery' }))
    fireEvent.click(screen.getByRole('button', { name: 'Send execution request' }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText(/The recovery request could not be completed/)).toBeInTheDocument()
    expect(onRequested).not.toHaveBeenCalled()
  })
})

describe('RecoveryPanel — recovery record', () => {
  it('presents a completed execution without claiming recovery success', () => {
    render(<RecoveryPanel {...baseProps} assessment={ok(assessment())} recovery={ok(recovery())} />)
    expect(
      screen.getByText(/Execution completed — recovery success not established/),
    ).toBeInTheDocument()
  })

  it('keeps proposed and executed actions as separate lists', () => {
    render(<RecoveryPanel {...baseProps} assessment={ok(assessment())} recovery={ok(recovery())} />)
    expect(screen.getByText('Proposed actions')).toBeInTheDocument()
    expect(screen.getByText('Executed actions')).toBeInTheDocument()
  })
})
