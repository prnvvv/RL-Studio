/**
 * Development mock adapter for verification records.
 *
 * Implements the planned Person 3 incident/verification contract (see
 * `schemas/verification.ts`) with deterministic fixtures that follow the
 * canonical warehouse reward-scaling demo scenario. Requires the explicit
 * `VITE_USE_MOCKS=true` opt-in and is fail-closed without it; every call site
 * must wrap results in `labeledMockData` so the UI shows the shared
 * `Sample data` label. Nothing here is presented as live backend behaviour.
 */
import type {
  AnomalyObservation,
  EvidenceReference,
  IncidentRecord,
  VerificationResult,
} from '../schemas/verification'
import { assertMocksEnabled } from './index'

/** The demo incident id the fixtures are anchored to. */
export const DEMO_INCIDENT_ID = 'inc_demo_warehouse_reward_scale'
/** Demo run id referenced by all fixtures. */
export const DEMO_RUN_ID = 'run_demo_warehouse_ppo'

/**
 * Fixed demo anchors, mirroring the canonical reward-scaling fault:
 * goal reward expected 100, observed 40 after the controlled fault.
 */
const EVT_GOAL_REWARD = 'evt_demo_step_812'
const EVT_GOAL_REWARD_AFTER = 'evt_demo_step_860'
const EVT_STEP_PENALTY = 'evt_demo_step_814'

const DEMO_INCIDENT: IncidentRecord = {
  incident_id: DEMO_INCIDENT_ID,
  schema_version: '1.0',
  run_id: DEMO_RUN_ID,
  requirement_id: 'req_demo_goal_reward',
  environment_id: 'warehouse_2d',
  environment_version: 'warehouse_v1',
  violation_type: 'reward_scale_mismatch',
  severity: 'high',
  status: 'open',
  detection_status: 'confirmed',
  diagnosis_status: 'unresolved',
  evidence_event_ids: [EVT_GOAL_REWARD, EVT_GOAL_REWARD_AFTER, EVT_STEP_PENALTY],
  evidence_refs: [EVT_GOAL_REWARD, EVT_GOAL_REWARD_AFTER, EVT_STEP_PENALTY],
  detector_id: 'deterministic_requirement_check',
  detector_version: '1.0',
  created_at: '2026-10-25T12:00:00Z',
  resolved_at: null,
}

const DEMO_VERIFICATION: VerificationResult = {
  verification_id: 'ver_demo_warehouse_reward_scale',
  overall_status: 'fail',
  summary:
    'One mandatory deterministic check failed: the observed goal reward 40 does not satisfy the confirmed requirement expecting 100.',
  results: [
    {
      requirement_id: 'req_demo_goal_reward',
      status: 'fail',
      expected: 100,
      actual: 40,
      tolerance: null,
      evidence_refs: [EVT_GOAL_REWARD, EVT_GOAL_REWARD_AFTER],
      details: {
        comparison_operator: '==',
        within_tolerance: false,
        requirement_source: 'developer_confirmed',
      },
      is_mandatory: true,
      timestamp: '2026-10-25T12:00:00Z',
    },
    {
      requirement_id: 'req_demo_step_penalty',
      status: 'pass',
      expected: -1,
      actual: -1,
      tolerance: null,
      evidence_refs: [EVT_STEP_PENALTY],
      details: {
        comparison_operator: '==',
        within_tolerance: true,
        requirement_source: 'developer_confirmed',
      },
      is_mandatory: false,
      timestamp: '2026-10-25T12:00:05Z',
    },
    {
      requirement_id: 'req_demo_observation_integrity',
      // No applicable expectation was recorded for this scope, so the honest
      // outcome is `unknown` — never a pass and never a violation.
      status: 'unknown',
      expected: null,
      actual: null,
      tolerance: null,
      evidence_refs: [],
      details: null,
      is_mandatory: false,
      timestamp: null,
    },
  ],
  evidence_refs: [EVT_GOAL_REWARD, EVT_GOAL_REWARD_AFTER, EVT_STEP_PENALTY],
  warnings: [
    'This fixture outcome is sample data; a real verdict requires a live incident record.',
  ],
  errors: [],
  timestamp: '2026-10-25T12:00:10Z',
  schema_version: '1.0',
}

const DEMO_EVIDENCE: EvidenceReference[] = [
  {
    id: EVT_GOAL_REWARD,
    source: 'event_id',
    run_identifier: DEMO_RUN_ID,
    environment_identifier: 'warehouse_v1',
    location: null,
    timestamp: '2026-10-25T11:58:40Z',
  },
  {
    id: EVT_GOAL_REWARD_AFTER,
    source: 'event_id',
    run_identifier: DEMO_RUN_ID,
    environment_identifier: 'warehouse_v1',
    location: null,
    timestamp: '2026-10-25T12:00:02Z',
  },
  {
    id: EVT_STEP_PENALTY,
    source: 'event_id',
    run_identifier: DEMO_RUN_ID,
    environment_identifier: 'warehouse_v1',
    location: null,
    timestamp: '2026-10-25T11:58:44Z',
  },
]

const DEMO_ANOMALIES: AnomalyObservation[] = [
  {
    anomaly_id: 'ano_demo_reward_deviation',
    anomaly_type: 'reward_deviation',
    score: 0.82,
    threshold: 0.5,
    description:
      'Goal-reward observations deviate from the recorded expectation across the affected interval.',
    evidence_refs: [EVT_GOAL_REWARD, EVT_GOAL_REWARD_AFTER],
    timestamp: '2026-10-25T12:00:12Z',
  },
]

export interface MockVerificationAdapter {
  getIncident(incidentId: string): Promise<IncidentRecord | null>
  getVerificationResult(incidentId: string): Promise<VerificationResult | null>
  listEvidence(incidentId: string): Promise<EvidenceReference[]>
  listAnomalies(incidentId: string): Promise<AnomalyObservation[]>
}

/**
 * Mock-mode adapter keyed by the demo incident id. Any other id resolves to
 * `null`, which the service layer turns into an honest `not_found` — the
 * fixtures never pretend arbitrary incidents exist.
 */
export const mockVerificationAdapter: MockVerificationAdapter = {
  async getIncident(incidentId) {
    assertMocksEnabled('verification.getIncident')
    return incidentId === DEMO_INCIDENT_ID ? DEMO_INCIDENT : null
  },
  async getVerificationResult(incidentId) {
    assertMocksEnabled('verification.getVerificationResult')
    return incidentId === DEMO_INCIDENT_ID ? DEMO_VERIFICATION : null
  },
  async listEvidence(incidentId) {
    assertMocksEnabled('verification.listEvidence')
    return incidentId === DEMO_INCIDENT_ID ? DEMO_EVIDENCE : []
  },
  async listAnomalies(incidentId: string) {
    assertMocksEnabled('verification.listAnomalies')
    return incidentId === DEMO_INCIDENT_ID ? DEMO_ANOMALIES : []
  },
}
