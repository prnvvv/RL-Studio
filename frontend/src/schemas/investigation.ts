/**
 * Investigation (AI diagnosis) contracts — @planned.
 *
 * Mirrors the investigation output semantics required by
 * `backend/AGENTS.md` §9.3 and the parsed result shapes in
 * `backend/verification/llm/response_parser.py` (ParsedEvidenceInvestigation).
 * The Person 3 investigation endpoints do not exist yet and the diagnosis
 * router is not mounted (`create_app` fact), so this file describes the
 * intended payload. Keep in sync once the shared schema is published.
 *
 * Truthfulness rules baked into the shape:
 * - Observed `facts` and model-generated `hypotheses` are separate arrays;
 *   presentation must never merge them.
 * - `confidence` is `null` unless the provider or a defined scoring method
 *   actually supplies one; when present it is an estimate, never a
 *   calibrated probability.
 * - A suggested action is a structured recommendation for Person 4; the
 *   frontend can never convert it into an executed action.
 */
import type { ISODateTime, UUID } from './shared'

/** One observed fact with the evidence references that support it. */
export interface InvestigationFact {
  statement: string
  evidence_refs: string[]
}

/** A model-proposed hypothesis — explicitly not a validated conclusion. */
export interface InvestigationHypothesis {
  hypothesis_id: UUID
  statement: string
  /** Model reasoning tied to specific evidence, or null. */
  reasoning: string | null
  supporting_evidence_refs: string[]
  /**
   * Provider/model-supplied confidence estimate, or `null` when the provider
   * does not supply one. Never invented by the frontend.
   */
  confidence: number | null
}

/**
 * A suggested corrective action from the structured recovery handoff
 * (`backend/AGENTS.md` §10). Actions come from the backend's allow-listed
 * set; `target` may be a checkpoint/record id when applicable.
 */
export interface SuggestedAction {
  action_type: string
  description: string
  target: string | null
  /** Whether the backend handoff marks this as needing human confirmation. */
  requires_confirmation: boolean
}

/** Provider identity actually recorded for the investigation, if known. */
export interface InvestigationProvider {
  /** Configured provider, e.g. 'meta_model_api'. Never invented per-call. */
  provider: string
  /**
   * Model identifier only when the backend recorded it; model names are never
   * assumed by the frontend.
   */
  model: string | null
  prompt_version: string | null
  schema_version: string | null
}

/** Complete investigation result for one incident. */
export interface InvestigationResult {
  investigation_id: UUID
  incident_id: string
  /** Concise key-observation summary, or null when the provider gave none. */
  summary: string | null
  /** Observed facts — distinct from hypotheses by construction. */
  facts: InvestigationFact[]
  /** Identified contradictions between evidence items. */
  contradictions: string[]
  hypotheses: InvestigationHypothesis[]
  /** Alternative explanations where reasonable. */
  alternatives: InvestigationHypothesis[]
  /** Recommended diagnostic tests. */
  recommended_tests: string[]
  suggested_action: SuggestedAction | null
  missing_evidence: string[]
  limitations: string[]
  /** Provider metadata when recorded; null when unavailable. */
  provider: InvestigationProvider | null
  created_at: ISODateTime | null
  schema_version: string
}

/**
 * Lived investigation state for the panel header, derived from what the
 * service actually reports — never from what "should" have happened.
 */
export type InvestigationState = 'no_record' | 'completed' | 'provider_unavailable' | 'failed'
