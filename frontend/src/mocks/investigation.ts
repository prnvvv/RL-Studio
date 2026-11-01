/**
 * Development mock adapter for AI investigations.
 *
 * Implements the planned investigation contract (see
 * `schemas/investigation.ts`). The fixtures separate observed facts from
 * model-generated hypotheses, and the demo investigation is NOT recorded
 * until `requestInvestigation` is called — the UI must never start out
 * showing an "analysis" that was never run, even as sample data.
 *
 * Requires the explicit `VITE_USE_MOCKS=true` opt-in (fail-closed); returned
 * payloads carry the shared `Sample data` label via the service layer.
 */
import type { InvestigationResult } from '../schemas/investigation'
import { assertMocksEnabled } from './index'
import { DEMO_INCIDENT_ID } from './verification'

const DEMO_INVESTIGATION: InvestigationResult = {
  investigation_id: 'inv_demo_warehouse_reward_scale',
  incident_id: DEMO_INCIDENT_ID,
  summary:
    'The deterministic checks are consistent with a changed goal-reward scale; observation corruption is not supported by the recorded evidence in this fixture.',
  facts: [
    {
      statement: 'Goal reward was observed as 40 where the confirmed requirement expects 100.',
      evidence_refs: ['evt_demo_step_812'],
    },
    {
      statement: 'The step-penalty check passed unchanged during the same interval.',
      evidence_refs: ['evt_demo_step_814'],
    },
  ],
  contradictions: [],
  hypotheses: [
    {
      hypothesis_id: 'hyp_demo_reward_scale_change',
      statement: 'The environment goal-reward scale changed during the recorded fault-injection interval.',
      reasoning:
        'Only goal-reward observations diverge while step-penalty checks stay within tolerance, which matches a scale change on the goal-reward path in this fixture.',
      supporting_evidence_refs: ['evt_demo_step_812', 'evt_demo_step_860'],
      // Provider-supplied in this fixture and always labelled as an estimate.
      confidence: 0.72,
    },
    {
      hypothesis_id: 'hyp_demo_observation_corruption',
      statement: 'Observation corruption caused systematic reward under-delivery.',
      reasoning: null,
      supporting_evidence_refs: [],
      // No scoring method supports a number here; honesty means null.
      confidence: null,
    },
  ],
  alternatives: [
    {
      hypothesis_id: 'hyp_demo_partial_training',
      statement: 'The policy simply undertrained on the new layout, without any environment fault.',
      reasoning: null,
      supporting_evidence_refs: [],
      confidence: null,
    },
  ],
  recommended_tests: [
    'Re-run evaluation episodes in the healthy environment configuration and compare the goal-reward distribution.',
    'Record observation checksum events for the affected episodes and re-run the integrity check.',
  ],
  suggested_action: {
    action_type: 'restore_checkpoint',
    description:
      'Assess the compatible pre-impact checkpoint recorded before the fault-injection interval; compatibility validation belongs to the recovery module.',
    target: 'ckpt_demo_pre_fault_1',
    requires_confirmation: true,
  },
  missing_evidence: [
    'No observation-checksum events are referenced for the affected episodes.',
    'No optimizer/normalization state snapshot is linked to the incident.',
  ],
  limitations: [
    'Sample data: this analysis was produced by deterministic fixtures, not the model provider.',
    'Model identity is not recorded, and hypotheses are estimates that do not establish cause.',
  ],
  provider: {
    provider: 'meta_model_api',
    model: null,
    prompt_version: null,
    schema_version: '1.0',
  },
  created_at: '2026-10-25T12:05:00Z',
  schema_version: '1.0',
}

export interface MockInvestigationAdapter {
  getInvestigation(incidentId: string): Promise<InvestigationResult | null>
  /** Records the demo investigation for the incident (explicit user action). */
  requestInvestigation(incidentId: string): Promise<InvestigationResult>
  /** Clears recorded investigations; used by tests against in-module state. */
  resetMockInvestigationState(): void
}

/** In-module "recorded investigations" keyed by incident id. */
let requested: Set<string> = new Set()

/**
 * Unknown incident ids fail loudly (`null` → service `not_found`); the demo
 * incident has no investigation until one is explicitly requested.
 */
export const mockInvestigationAdapter: MockInvestigationAdapter = {
  async getInvestigation(incidentId) {
    assertMocksEnabled('investigation.getInvestigation')
    if (incidentId !== DEMO_INCIDENT_ID) return null
    return requested.has(incidentId) ? DEMO_INVESTIGATION : null
  },
  async requestInvestigation(incidentId) {
    assertMocksEnabled('investigation.requestInvestigation')
    if (incidentId !== DEMO_INCIDENT_ID) {
      throw new Error(`No demo investigation fixture exists for incident "${incidentId}".`)
    }
    requested.add(incidentId)
    return DEMO_INVESTIGATION
  },
  resetMockInvestigationState() {
    requested = new Set()
  },
}
