/**
 * Intent & requirement contracts — @planned.
 *
 * The backend intent/requirement endpoints do not exist yet (Person 3 owns
 * them; see frontend/AGENTS.md §3.3 and docs/API_INTEGRATION.md). These types
 * describe the agreed-intent payload this frontend submits and renders, so
 * mock adapters and presentation are already bound to the intended domain
 * structure. Once Person 3 publishes the shared schema, this file must be
 * updated to mirror it exactly ("keep in sync" rule, `schemas/shared.ts`).
 *
 * Semantics follow root AGENTS.md §7.3: a requirement records its source and
 * confirmation status explicitly; front-end types never turn a draft into a
 * confirmed contract and never invent expected values.
 */
import type { ISODateTime, UUID } from './shared'

/** Where a requirement's authority comes from (root AGENTS.md §7.3). */
export type RequirementSource = 'developer_confirmed' | 'test_derived' | 'code_inferred'

/** Frontend review flow state, kept separate from the backend's contract states. */
export type RequirementReviewState = 'draft' | 'confirmed' | 'rejected'

/**
 * Outcome of submitting natural-language intent for extraction.
 *
 * - `accepted`: requirements extracted and awaiting review.
 * - `ambiguous`: the text matched the domain but could not be parsed
 *   unambiguously; `warnings` explains what could not be resolved.
 * - `unsupported`: outside the supported domain; no requirements extracted.
 */
export type IntentExtractionStatus = 'accepted' | 'ambiguous' | 'unsupported'

export interface IntentSubmissionRequest {
  schema_version: string
  /** Free-form intent statement in natural language. */
  text: string
}

export interface ExtractedRequirementDraft {
  /**
   * Stable requirement id. `null` while drafts are only client-side; the
   * backend assigns ids as part of a persisted requirement lifecycle.
   */
  requirement_id: UUID | null
  /** Human-readable statement of the expected behaviour. */
  description: string
  /** Machine-checkable rule type where extraction succeeded, else null. */
  rule_type: string | null
  /** Rule parameters where extraction succeeded, else null. */
  parameters: Record<string, unknown> | null
  /** Lower tolerance/epsilon where the rule type supports one. */
  tolerance: number | null
  /** Never inferred locally: as reported by the extraction provider. */
  source: RequirementSource
  /**
   * Backend-checkable confirmation status. null in returned drafts because
   * nothing is persisted until the review decision is submitted.
   */
  confirmed: boolean | null
  /**
   * Environment version the extraction says this draft applies to, or null
   * when the statement did not bound a scope.
   */
  environment_version: string | null
}

export interface IntentSubmissionResult {
  schema_version: string
  extraction_status: IntentExtractionStatus
  /** Empty for unsupported; non-empty explains ambiguous parse failures. */
  warnings: string[]
  requirements: ExtractedRequirementDraft[]
  /** Server timestamp of the submission, if the provider supplies one. */
  timestamp: ISODateTime | null
}

export interface RequirementRecord extends ExtractedRequirementDraft {
  requirement_id: UUID
  confirmed: boolean
  source_version: string | null
  created_at: ISODateTime | null
}

/** Review decision for a draft requirement. */
export type RequirementDecision = 'confirm' | 'reject'
