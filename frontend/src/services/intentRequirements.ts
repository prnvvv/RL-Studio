/**
 * Intent & requirements service (@planned contract).
 *
 * The Person 3 backend endpoints do not exist yet. Two modes:
 *
 * - `VITE_USE_MOCKS=true`: delegates to the labeled mock adapter
 *   (`src/mocks/intentRequirements.ts`) and returns payloads wrapped in
 *   `MockData`, carrying the shared `Sample data` label.
 * - otherwise: issues real HTTP calls against the documented planned paths
 *   below. Until those endpoints are implemented the caller receives honest
 *   `not_found` / `unavailable` error results — the UI must render them as a
 *   pending-backend state, never as empty data (§16.2).
 *
 * Paths are annotated `@planned` and must be confirmed with the backend owner
 * before any production binding. The mock/real switch is interface-level only
 * so presentation stays unchanged across it.
 */
import type {
  IntentSubmissionRequest,
  IntentSubmissionResult,
  RequirementDecision,
  RequirementRecord,
} from '../schemas/intent'
import type { MockData } from '../mocks/index'
import type { ServiceResult } from './types'
import { api } from './client'
import { mocksEnabled } from '../mocks/index'
import { mockIntentRequirementsAdapter } from '../mocks/intentRequirements'

/** @planned POST intent text for extraction. */
export const INTENT_SUBMIT_PATH = '/api/v1/intents'
/** @planned list of previously confirmed/rejected requirements. */
export const REQUIREMENTS_LIST_PATH = '/api/v1/requirements'
/** @planned record a review decision for a requirement draft. */
export function requirementDecisionPath(requirementId: string): string {
  return `/api/v1/requirements/${encodeURIComponent(requirementId)}/review-decision`
}

export type IntentSubmissionOutcome = ServiceResult<IntentSubmissionResult | MockData<IntentSubmissionResult>>

export interface IntentRequirementsService {
  submitIntent(text: string): Promise<IntentSubmissionOutcome>
  listRequirements(): Promise<ServiceResult<RequirementRecord[] | MockData<RequirementRecord[]>>>
  decideRequirement(
    requirementId: string,
    decision: RequirementDecision,
  ): Promise<ServiceResult<RequirementRecord | MockData<RequirementRecord>>>
}

/** Real-mode calls against the planned endpoints; returns honest errors until they exist. */
const realAdapter: IntentRequirementsService = {
  submitIntent(text: string) {
    const request: IntentSubmissionRequest = { schema_version: '1.0', text }
    return api.post<IntentSubmissionResult>(INTENT_SUBMIT_PATH, { jsonBody: request })
  },
  listRequirements() {
    return api.get<RequirementRecord[]>(REQUIREMENTS_LIST_PATH)
  },
  decideRequirement(requirementId: string, decision: RequirementDecision) {
    return api.post<RequirementRecord>(requirementDecisionPath(requirementId), { jsonBody: { decision } })
  },
}

/** Mock-mode adapter; payloads carry the shared `Sample data` label. */
const mockedAdapter: IntentRequirementsService = {
  async submitIntent(text) {
    const outcome = await mockIntentRequirementsAdapter.submitIntent(text)
    return { state: 'ok', data: outcome }
  },
  async listRequirements() {
    const outcome = await mockIntentRequirementsAdapter.listRequirements()
    return { state: 'ok', data: outcome }
  },
  async decideRequirement(requirementId, decision) {
    const outcome = await mockIntentRequirementsAdapter.decideRequirement(requirementId, decision)
    return { state: 'ok', data: outcome }
  },
}

/** Select the adapter from the mock opt-in flag. */
export function createIntentRequirementsService(): IntentRequirementsService {
  return mocksEnabled() ? mockedAdapter : realAdapter
}
