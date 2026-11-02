import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ImpactAnalysis, ProvenanceTrace } from '../../schemas/provenance'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'
import type { MockData } from '../../mocks'
import { ProvenanceView } from './ProvenanceView'

const TRACE: ProvenanceTrace = {
  provenance_id: 'prov_demo',
  run_id: 'run_demo',
  provenance_status: 'complete',
  lineage_completeness: 'complete',
  source_environment_version: 'warehouse_v1',
  environment_id: 'warehouse',
  environment_version: 'warehouse_v1',
  artifact_count: 2,
  artifacts: [
    {
      artifact_id: 'ckpt_pre_impact',
      run_id: 'run_demo',
      artifact_type: 'checkpoint',
      artifact_path: '/checkpoints/ckpt_pre_impact.zip',
      artifact_hash: 'abc123',
      artifact_version: '1',
      artifact_status: 'available',
      artifact_created_at: '2026-11-02T00:00:00Z',
      parent_artifact_id: null,
      checkpoint_id: 'ckpt_pre_impact',
      checkpoint_path: '/checkpoints/ckpt_pre_impact.zip',
      policy_version: null,
      trajectory_id: null,
      experience_id: null,
      policy_update_id: null,
      environment_id: 'warehouse',
      environment_version: 'warehouse_v1',
      agent_config_fingerprint: 'fp_1',
      episode_id: null,
      timestep: null,
      update_index: null,
      included_state_components: ['policy', 'optimizer'],
      integrity_status: 'verified',
      metadata_schema_version: '1.0',
      metadata: {},
      created_at: '2026-11-02T00:00:00Z',
      updated_at: '2026-11-02T00:00:00Z',
    },
    {
      artifact_id: 'ckpt_mid_fault',
      run_id: 'run_demo',
      artifact_type: 'checkpoint',
      artifact_path: '/checkpoints/ckpt_mid_fault.zip',
      artifact_hash: 'def456',
      artifact_version: '2',
      artifact_status: 'available',
      artifact_created_at: '2026-11-02T00:01:00Z',
      parent_artifact_id: 'ckpt_pre_impact',
      checkpoint_id: 'ckpt_mid_fault',
      checkpoint_path: '/checkpoints/ckpt_mid_fault.zip',
      policy_version: null,
      trajectory_id: null,
      experience_id: null,
      policy_update_id: null,
      environment_id: 'warehouse',
      environment_version: 'warehouse_v1',
      agent_config_fingerprint: 'fp_1',
      episode_id: null,
      timestep: null,
      update_index: null,
      included_state_components: ['policy', 'optimizer'],
      integrity_status: 'unverified',
      metadata_schema_version: '1.0',
      metadata: {},
      created_at: '2026-11-02T00:01:00Z',
      updated_at: '2026-11-02T00:01:00Z',
    },
  ],
  links: [
    {
      link_id: 'link_1',
      run_id: 'run_demo',
      from_artifact_id: 'ckpt_pre_impact',
      to_artifact_id: 'ckpt_mid_fault',
      relation: 'derived_from',
      created_at: '2026-11-02T00:01:00Z',
    },
  ],
  warnings: ['Trajectory artifacts before episode 3 were not recorded.'],
  evidence_ids: [],
  details: {},
  created_at: '2026-11-02T00:00:00Z',
  updated_at: '2026-11-02T00:01:00Z',
}

const IMPACT: Omit<ImpactAnalysis, 'impact_status'> & {
  impact_status: ImpactAnalysis['impact_status']
} = {
  impact_id: 'impact_demo',
  incident_id: 'inc_demo',
  run_id: 'run_demo',
  impact_status: 'potentially_affected',
  impact_score: null,
  source_environment_version: 'warehouse_v1',
  corruption_start_timestep: 1200,
  corruption_end_timestep: 1400,
  affected_artifact_ids: ['ckpt_mid_fault'],
  affected_trajectory_ids: ['traj_3'],
  affected_policy_update_ids: [],
  affected_checkpoint_ids: ['ckpt_mid_fault'],
  evidence_ids: ['evt_1'],
  warnings: [],
  errors: [],
  details: {},
  created_at: '2026-11-02T00:02:00Z',
  completed_at: '2026-11-02T00:02:30Z',
}

type PanelState<T> = ServiceQueryState<T | MockData<T>>

function ok<T>(data: T): PanelState<T> {
  return { state: 'ok', data }
}

function loading<T>(): PanelState<T> {
  return { state: 'loading' }
}

function error<T>(): PanelState<T> {
  return {
    state: 'error',
    error: { kind: 'network', message: 'The studio service is unreachable right now.' },
    data: null,
  }
}

describe('ProvenanceView — trace', () => {
  it('renders loading skeleton while the trace loads', () => {
    render(<ProvenanceView trace={loading<ProvenanceTrace>()} />)
    // LoadingSkeleton announces itself; no fabricated values appear.
    expect(screen.queryByText(TRACE.provenance_id)).not.toBeInTheDocument()
  })

  it('renders the recorded status badges, artifacts, links, and warnings verbatim', () => {
    render(<ProvenanceView trace={ok(TRACE)} />)

    expect(screen.getByText('Provenance: complete')).toBeInTheDocument()
    expect(screen.getByText('Lineage: complete')).toBeInTheDocument()
    expect(screen.getByText('Recorded artifacts (2)')).toBeInTheDocument()
    expect(screen.getByText('ckpt_pre_impact')).toBeInTheDocument()
    expect(screen.getByText(/1 lineage link recorded/)).toBeInTheDocument()
    expect(screen.getByText(/Warning: Trajectory artifacts before episode 3/)).toBeInTheDocument()
    // Distinct artifact statuses are displayed as text, not inferred.
    expect(screen.getByText('Integrity: verified')).toBeInTheDocument()
    expect(screen.getByText('Integrity: unverified')).toBeInTheDocument()
  })

  it('makes an empty trace honest instead of implying coverage', () => {
    const empty: ProvenanceTrace = { ...TRACE, artifacts: [], links: [], artifact_count: 0 }
    render(<ProvenanceView trace={ok(empty)} />)
    expect(screen.getByText(/No artifacts are recorded in this trace/)).toBeInTheDocument()
    expect(screen.getByText(/No lineage links are recorded/)).toBeInTheDocument()
  })

  it('renders an honest error with a retry affordance when the fetch fails', () => {
    const onReloadTrace = vi.fn()
    render(<ProvenanceView trace={error<ProvenanceTrace>()} onReloadTrace={onReloadTrace} />)

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/The provenance record could not be loaded/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onReloadTrace).toHaveBeenCalledTimes(1)
  })
})

describe('ProvenanceView — impact classifications', () => {
  it.each([
    ['confirmed_exposed', 'Impact: confirmed exposed'],
    ['potentially_affected', 'Impact: potentially affected'],
    ['not_exposed_based_on_recorded_lineage', 'Not exposed based on recorded lineage'],
    ['unknown_incomplete_lineage', 'Impact unknown — incomplete lineage'],
  ] as const)('renders %s as its own distinct claim', (status, label) => {
    render(<ProvenanceView trace={ok(TRACE)} impact={ok({ ...IMPACT, impact_status: status })} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('adds the explicit counter-claim only for unknown lineage', () => {
    render(
      <ProvenanceView
        trace={ok(TRACE)}
        impact={ok({ ...IMPACT, impact_status: 'unknown_incomplete_lineage' })}
      />,
    )
    expect(
      screen.getByText(/This is an unknown result, not a statement that artifacts are unaffected/),
    ).toBeInTheDocument()
    expect(screen.getByText(/not an unaffected claim/)).toBeInTheDocument()
  })

  it('limits the unaffected wording to recorded lineage and shows affected counts', () => {
    render(
      <ProvenanceView
        trace={ok(TRACE)}
        impact={ok({ ...IMPACT, impact_status: 'potentially_affected' })}
      />,
    )
    expect(
      screen.getByText(
        /Recorded as affected: 1 artifact, 1 trajectory, 0 policy updates, 1 checkpoint/,
      ),
    ).toBeInTheDocument()
    expect(screen.getByText(/Corruption window: timesteps 1200–1400/)).toBeInTheDocument()
    // The unaffected counter-claim paragraph belongs only to the unknown status.
    expect(
      screen.queryByText(/not a statement that artifacts are unaffected/),
    ).not.toBeInTheDocument()
  })

  it('renders an independent loading/error state for the impact record', () => {
    render(<ProvenanceView trace={ok(TRACE)} impact={error<ImpactAnalysis>()} />)
    expect(screen.getByText(/The impact analysis could not be loaded/)).toBeInTheDocument()
  })

  it('omits the impact section entirely when no incident impact is requested', () => {
    render(<ProvenanceView trace={ok(TRACE)} />)
    expect(screen.queryByRole('region', { name: 'Incident impact' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Incident impact analysis/)).not.toBeInTheDocument()
  })
})
