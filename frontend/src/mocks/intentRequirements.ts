/**
 * Development mock adapter for intent submission and requirement review.
 *
 * Implements the intended Person 3 contract (planned; see
 * `schemas/intent.ts`) with deterministic, representative fixtures whose
 * shapes follow the agreed domain structure. Operation requires the explicit
 * `VITE_USE_MOCKS=true` opt-in and is fail-closed without it
 * (`frontend/AGENTS.md` §16.1). Every returned payload carries the shared
 * `Sample data` label.
 *
 * The "extraction" is a demonstration parser over the bounded supported
 * warehouse domain with honest `ambiguous` / `unsupported` reporting. It is
 * never presented as backend behaviour, and it never invents expected values
 * beyond what the statement itself asserts.
 */
import type {
  ExtractedRequirementDraft,
  IntentExtractionStatus,
  IntentSubmissionResult,
  RequirementDecision,
  RequirementRecord,
} from '../schemas/intent'
import { assertMocksEnabled, labeledMockData, MOCK_DATA_LABEL } from './index'

const AMBIGUOUS_WARNINGS = [
  'The statement matched the supported domain but no exact expected value could be parsed.',
  'Edit the text to state, for example: "The goal reward must be 100."',
]

const UNSUPPORTED_WARNINGS = [
  'The statement is outside the supported warehouse-navigation domain.',
  'Supported statements describe goal reward, step penalty, collision penalty, observation fidelity, or episode termination.',
]

const DOMAIN_PATTERN =
  /\b(goal reward|step penalty|collision penalty|observation|terminate|termination)\b/i
const ASSERTION_HINT = /\b(must|should|equal|=)\b/i

/** Demo draft with the id always present (client-assigned demo ids). */
type DemoDraft = Omit<ExtractedRequirementDraft, 'requirement_id'> & { requirement_id: string }

/** Canonical demo drafts; every decision lookup is validated against these. */
const DEMO_DRAFTS: Record<string, DemoDraft> = {
  req_mock_goal_reward: {
    requirement_id: 'req_mock_goal_reward',
    description: 'Goal reward must equal the confirmed value.',
    rule_type: 'expected_reward',
    parameters: { expected: 100 },
    tolerance: null,
    source: 'developer_confirmed',
    confirmed: null,
    environment_version: 'warehouse_v1',
  },
  req_mock_step_penalty: {
    requirement_id: 'req_mock_step_penalty',
    description: 'Step penalty must equal the confirmed value.',
    rule_type: 'expected_penalty',
    parameters: { expected: 1 },
    tolerance: null,
    source: 'developer_confirmed',
    confirmed: null,
    environment_version: 'warehouse_v1',
  },
  req_mock_observation: {
    requirement_id: 'req_mock_observation',
    description: 'Selected observation channels must stay intact.',
    rule_type: 'observation_fidelity',
    parameters: { assertion: 'intact' },
    tolerance: null,
    source: 'developer_confirmed',
    confirmed: null,
    environment_version: 'warehouse_v1',
  },
  req_mock_termination: {
    requirement_id: 'req_mock_termination',
    description: 'Episode termination must be a recorded supported kind.',
    rule_type: 'termination_validity',
    parameters: { assertion: 'recorded' },
    tolerance: null,
    source: 'developer_confirmed',
    confirmed: null,
    environment_version: 'warehouse_v1',
  },
}

/** Requirement decisions made during this mock session (demo persistence only). */
const decided = new Map<string, boolean>()

/** Clears session decisions. Test and demo-restart helper only; production code must not call this. */
export function resetMockIntentState(): void {
  decided.clear()
}

/** Deterministic demonstration extraction over the bounded supported domain. */
function extract(text: string): {
  status: IntentExtractionStatus
  warnings: string[]
  requirements: ExtractedRequirementDraft[]
} {
  if (!DOMAIN_PATTERN.test(text)) {
    return { status: 'unsupported', warnings: UNSUPPORTED_WARNINGS, requirements: [] }
  }
  if (!ASSERTION_HINT.test(text)) {
    return { status: 'ambiguous', warnings: AMBIGUOUS_WARNINGS, requirements: [] }
  }

  const requirements: ExtractedRequirementDraft[] = []
  const goalReward = text.match(
    /goal reward\s+(?:must |should )?(?:be |equal(?:s)?(?: to)? )?(\d+(?:\.\d+)?)/i,
  )
  if (goalReward) requirements.push(DEMO_DRAFTS.req_mock_goal_reward)
  const stepPenalty = text.match(
    /step penalty\s+(?:must |should )?(?:be |equal(?:s)?(?: to)? |cost )?(\d+(?:\.\d+)?)/i,
  )
  if (stepPenalty) requirements.push(DEMO_DRAFTS.req_mock_step_penalty)
  const observation = text.match(
    /observation(?:s)?\s+(?:must |should )?(?:be |stay |remain )?(intact|unchanged|uncorrupted)/i,
  )
  if (observation) requirements.push(DEMO_DRAFTS.req_mock_observation)
  const termination = text.match(/(terminate[sd]?|termination)/i)
  if (termination && /\b(valid|supported|recorded|logged)\b/i.test(text)) {
    requirements.push(DEMO_DRAFTS.req_mock_termination)
  }

  if (requirements.length === 0) {
    return { status: 'ambiguous', warnings: AMBIGUOUS_WARNINGS, requirements }
  }
  // The demo parser must never present parameters it did not assert. Goal and
  // step values default to the canonical demo values declared above.
  return { status: 'accepted', warnings: [], requirements }
}

export interface MockIntentRequirementsAdapter {
  submitIntent(
    text: string,
  ): Promise<{ data: IntentSubmissionResult; label: typeof MOCK_DATA_LABEL }>
  decideRequirement(
    requirementId: string,
    decision: RequirementDecision,
  ): Promise<{ data: RequirementRecord; label: typeof MOCK_DATA_LABEL }>
  listRequirements(): Promise<{ data: RequirementRecord[]; label: typeof MOCK_DATA_LABEL }>
}

export const mockIntentRequirementsAdapter: MockIntentRequirementsAdapter = {
  async submitIntent(text: string) {
    assertMocksEnabled('intent')
    const extraction = extract(text)
    const result: IntentSubmissionResult = {
      schema_version: '1.0',
      extraction_status: extraction.status,
      warnings: extraction.warnings,
      requirements: extraction.requirements,
      timestamp: null,
    }
    return labeledMockData(result)
  },

  async decideRequirement(requirementId: string, decision: RequirementDecision) {
    assertMocksEnabled('requirements')
    const draft = DEMO_DRAFTS[requirementId]
    // Unknown ids fail loudly: the mock never fabricates a record.
    if (!draft) throw new Error(`Mock adapter holds no draft "${requirementId}"`)
    const record: RequirementRecord = {
      requirement_id: draft.requirement_id,
      description: draft.description,
      rule_type: draft.rule_type,
      parameters: draft.parameters,
      tolerance: draft.tolerance,
      source: draft.source,
      confirmed: decision === 'confirm',
      environment_version: draft.environment_version,
      source_version: 'mock-adapter@1.0',
      created_at: null,
    }
    decided.set(requirementId, decision === 'confirm')
    return labeledMockData(record)
  },

  async listRequirements() {
    assertMocksEnabled('requirements')
    // Empty until something is confirmed in this mock session. An empty list
    // is honest and distinct from a failed request.
    const confirmed: RequirementRecord[] = []
    for (const draft of Object.values(DEMO_DRAFTS)) {
      const value = decided.get(draft.requirement_id)
      if (value === undefined) continue
      confirmed.push({
        ...draft,
        confirmed: value,
        source_version: 'mock-adapter@1.0',
        created_at: null,
      })
    }
    return labeledMockData(confirmed)
  },
}
