/**
 * Verification & incident contracts — @planned for the frontend.
 *
 * Mirrors `backend/verification/models.py` (CheckStatus, VerificationCheckResult,
 * VerificationResult, EvidenceReference, AnomalyObservation) and
 * `shared/schemas/contracts.py` (Incident). The Person 3 incident/verification
 * API endpoints do not exist yet and the diagnosis router is not mounted in
 * `create_app`, so this file describes the intended payload the D&R page will
 * render. Once Person 3 publishes the shared frontend-facing schema, this file
 * must be updated to mirror it exactly ("keep in sync" rule).
 *
 * Semantics enforced here (root AGENTS.md §7.3–7.4, backend/AGENTS.md §6):
 * - `unknown` / `blocked` check outcomes are NEVER convertible into pass/fail
 *   on the frontend; a missing expectation is `unknown`, never a pass.
 * - Detection status, diagnosis status, and incident resolution remain three
 *   separate state dimensions.
 */
import type { ISODateTime, UUID } from './shared'

/**
 * Deterministic check outcome (`VerificationCheckResult.status`).
 * Mirrors the backend `CheckStatus` enum exactly.
 */
export type CheckStatus = 'pass' | 'fail' | 'pending' | 'unknown' | 'blocked' | 'error'

/** Incident workflow status (`shared/schemas/contracts.py#IncidentStatus`). */
export type IncidentStatus = 'open' | 'investigating' | 'resolved' | 'wont_fix' | 'false_positive'

/** Incident severity (`shared/schemas/contracts.py#ViolationSeverity`). */
export type ViolationSeverity = 'low' | 'medium' | 'high' | 'critical'

/**
 * Root-cause claim separate from detection
 * (`shared/schemas/contracts.py#RootCauseStatus`).
 */
export type RootCauseStatus = 'confirmed' | 'probable' | 'unresolved'

/** Detection claim (`Incident.detection_status`): a violation vs a suspicion. */
export type DetectionStatus = 'confirmed' | 'suspected' | 'unresolved'

/** A stable reference to a piece of execution evidence (`EvidenceReference`). */
export interface EvidenceReference {
  id: UUID
  /** What produced it, e.g. 'run_id', 'checkpoint_id', 'event_id'. */
  source: string
  run_identifier: string | null
  environment_identifier: string | null
  /** Reference/path rather than a raw payload, or null when not recorded. */
  location: string | null
  timestamp: ISODateTime | null
}

/** One requirement evaluated against evidence (`VerificationCheckResult`). */
export interface VerificationCheckResult {
  requirement_id: string
  status: CheckStatus
  /**
   * The expected value from the active requirement. Absent expectations are
   * declared `unknown` at the check level and must not be displayed as a pass.
   */
  expected: unknown
  /** The observed value from execution evidence. */
  actual: unknown
  tolerance: number | null
  /** EvidenceReference ids backing this result. */
  evidence_refs: string[]
  /** Free-form check details (never secrets, never raw prompts). */
  details: Record<string, unknown> | null
  /** Whether failing/blocking this check forbids an overall PASS. */
  is_mandatory: boolean
  timestamp: ISODateTime | null
}

/** Aggregated deterministic verification result (`VerificationResult`). */
export interface VerificationResult {
  verification_id: UUID
  overall_status: CheckStatus
  summary: string | null
  /** Ordered per-requirement results (backend stores a map; order is presentation data). */
  results: VerificationCheckResult[]
  /** Top-level EvidenceReference ids. */
  evidence_refs: string[]
  warnings: string[]
  errors: string[]
  timestamp: ISODateTime | null
  schema_version: string
}

/** Detector output types (`AnomalyObservation`), distinct from confirmed faults. */
export type AnomalyType =
  'statistical' | 'distribution_shift' | 'reward_deviation' | 'observation_corruption'

/**
 * Anomaly signal (`AnomalyObservation`) — a detector's output is NOT a
 * confirmed fault and must never be displayed as one without a deterministic
 * check behind it.
 */
export interface AnomalyObservation {
  anomaly_id: UUID | null
  anomaly_type: AnomalyType
  /** Normalized 0..1 score where the detector supplies one, else null. */
  score: number | null
  threshold: number | null
  description: string | null
  evidence_refs: string[]
  timestamp: ISODateTime | null
}

/**
 * A detected contract violation with evidence, separate from diagnosis
 * (`shared/schemas/contracts.py#Incident`). @planned: no incident endpoints
 * exist yet (backend/AGENTS.md §12); this schema is mirrored ahead of them.
 */
export interface IncidentRecord {
  incident_id: UUID
  schema_version: string
  run_id: string
  requirement_id: string | null
  environment_id: string | null
  environment_version: string | null
  /** Stable violation category, e.g. 'reward_scale_mismatch'. */
  violation_type: string
  severity: ViolationSeverity
  status: IncidentStatus
  detection_status: DetectionStatus
  diagnosis_status: RootCauseStatus
  evidence_event_ids: string[]
  evidence_refs: string[]
  detector_id: string | null
  detector_version: string | null
  created_at: ISODateTime | null
  resolved_at: ISODateTime | null
}
