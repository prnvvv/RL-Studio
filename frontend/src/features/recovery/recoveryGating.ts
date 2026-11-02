/**
 * Recovery gating and status presentation — derived, deterministic.
 *
 * Pure functions translating the backend recovery contracts into the minimal
 * presentation decisions the UI is ALLOWED to make. Nothing here authorizes a
 * restore: the backend owns compatibility, lineage, and eligibility. The
 * frontend only enforces "do not offer what the record does not support".
 *
 * Hard rules enforced (root AGENTS.md §13):
 * - A missing or unknown assessment is a gate CLOSED, never a soft pass.
 * - A completed execution is not a successful recovery: success claims only
 *   exist where the evaluation record states them.
 * - `proposed -> approved -> executing/executed -> evaluated` remain
 *   distinguishable steps in the presentation.
 */
import type {
  Recovery,
  RecoveryAssessment,
  RecoveryCompatibilityCheck,
  RecoveryStatus,
} from '../../schemas/recovery'

export interface AssessmentGate {
  /** The UI may offer an execution request subject to approval. */
  canRequestExecution: boolean
  /** One-sentence reason shown next to the gate. */
  reason: string
  /** True when every recorded compatibility check passed. */
  allChecksPassed: boolean
}

/**
 * Derive the execution-request gate from a recorded assessment.
 *
 * Only `eligible` AND every recorded check `pass` opens the gate. Any `fail`
 * blocks; `blocked`/`unknown`/`skipped` checks are never treated as passes;
 * `needs_review` / `ineligible` / `unknown` eligibility never opens the gate.
 * An absence of checks (empty list) is NOT a pass — records must state it.
 */
export function assessmentGate(assessment: RecoveryAssessment | null): AssessmentGate {
  if (!assessment) {
    return {
      canRequestExecution: false,
      reason: 'No recorded assessment exists; nothing is offered until the backend records one.',
      allChecksPassed: false,
    }
  }

  const { recovery_eligibility: eligibility, compatibility } = assessment

  if (eligibility !== 'eligible') {
    return {
      canRequestExecution: false,
      reason:
        eligibility === 'ineligible'
          ? 'The backend recorded this recovery as ineligible.'
          : eligibility === 'needs_review'
            ? 'The backend requires review before any recovery request may be made.'
            : 'The backend eligibility is unknown, so the gate stays closed.',
      allChecksPassed: false,
    }
  }

  if (compatibility.length === 0) {
    return {
      canRequestExecution: false,
      reason: 'The assessment records no compatibility checks, so nothing may be requested.',
      allChecksPassed: false,
    }
  }

  const failing = compatibility.filter((check) => check.outcome !== 'pass')
  if (failing.length > 0) {
    const blocking =
      failing.find((check) => check.outcome === 'fail') ??
      (failing[0] as RecoveryCompatibilityCheck)
    return {
      canRequestExecution: false,
      reason: `A recorded compatibility check did not pass (${blocking.name}: ${blocking.outcome}).`,
      allChecksPassed: false,
    }
  }

  return {
    canRequestExecution: true,
    reason: 'The recorded assessment is eligible with all compatibility checks passed.',
    allChecksPassed: true,
  }
}

export type RecoveryPresentation =
  | 'proposed'
  | 'approved'
  | 'executing'
  | 'executed_completed'
  | 'executed_failed'
  | 'blocked'
  | 'cancelled'
  | 'evaluated'

/**
 * Map the backend lifecycle state onto an explicit presentation. `completed`
 * maps to "executed_completed" deliberately: execution finished is NOT
 * recovery success; only the evaluation record can make that claim.
 */
export function recoveryPresentation(status: RecoveryStatus): RecoveryPresentation {
  switch (status) {
    case 'proposed':
      return 'proposed'
    case 'approved':
      return 'approved'
    case 'executing':
      return 'executing'
    case 'completed':
      return 'executed_completed'
    case 'failed':
      return 'executed_failed'
    case 'blocked':
      return 'blocked'
    case 'cancelled':
      return 'cancelled'
    case 'evaluated':
      return 'evaluated'
  }
}

export interface RecoverySuccessClaim {
  label: string
  tone: 'neutral' | 'strong' | 'quiet'
  /** `executed` / `successful` / `failed` / `inconclusive` are distinct claims. */
  claim: 'executed' | 'successful' | 'not_successful' | 'inconclusive' | 'unknown'
}

/**
 * What the UI may say about recovery outcome for a recovery record alone.
 * Without an evaluation record the claim is "executed" at most — never
 * "successful".
 */
export function recoveryOutcomeClaim(record: Recovery): RecoverySuccessClaim {
  const presentation = recoveryPresentation(record.recovery_status)
  switch (presentation) {
    case 'executed_completed':
      return {
        label: 'Execution completed — recovery success not established',
        tone: 'neutral',
        claim: 'executed',
      }
    case 'executing':
      return { label: 'Execution in progress', tone: 'neutral', claim: 'unknown' }
    case 'executed_failed':
      return { label: 'Execution failed', tone: 'strong', claim: 'not_successful' }
    case 'blocked':
      return { label: 'Recovery blocked', tone: 'quiet', claim: 'unknown' }
    case 'cancelled':
      return { label: 'Recovery cancelled', tone: 'quiet', claim: 'unknown' }
    // `evaluated` is the lifecycle state, not the verdict; the evaluation
    // SUMMARY record supplies the actual claim.
    case 'evaluated':
    case 'proposed':
    case 'approved':
      return {
        label: 'Recovery proposed; no execution result yet',
        tone: 'quiet',
        claim: 'unknown',
      }
  }
}

/** Human labels for allow-listed strategies (presentation only). */
export function strategyLabel(strategy: Recovery['recovery_strategy']): string {
  const labels: Record<Recovery['recovery_strategy'], string> = {
    restore_checkpoint: 'Restore checkpoint',
    correct_environment_config: 'Correct environment configuration',
    discard_pending_rollouts: 'Discard incompatible pending rollouts',
    continue_with_fresh_experience: 'Continue with fresh experience',
    evaluate_only: 'Evaluate only',
  }
  return labels[strategy]
}
