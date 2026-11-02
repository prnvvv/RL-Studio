/**
 * Provenance contracts — LIVE Person 4 endpoints.
 *
 * Mirrors `backend/provenance/models.py` exactly as served by the mounted
 * `provenance.p4_router` (`backend/api/routers/provenance.py`):
 * - `GET /api/v1/runs/{run_id}/provenance`     -> ProvenanceTrace
 * - `GET /api/v1/runs/{run_id}/artifacts`      -> RunArtifactList
 * - `GET /api/v1/artifacts/{artifact_id}`      -> Artifact
 * - `GET /api/v1/incidents/{incident_id}/impact` -> ImpactAnalysis
 *
 * Note: mounting `include_in_schema` registration is in `app.create_app`;
 * these are real documented endpoints, not planned ones. The canonical parity
 * rule applies: keep this file in sync exactly with the backend models.
 *
 * Semantic guards carried over from the backend (`frontend/AGENTS.md` §14.1):
 * - `unknown_incomplete_lineage` means "impact unknown", never "unaffected".
 * - Exposure and causal damage are different claims and are never merged.
 */
import type { ISODateTime } from './shared'

/** Artifact category (`ArtifactType`). */
export type ArtifactType =
  | 'checkpoint'
  | 'trajectory'
  | 'experience'
  | 'policy_update'
  | 'configuration'
  | 'log'
  | 'dataset'
  | 'other'

/** Artifact availability (`ArtifactStatus`). */
export type ArtifactStatus =
  'available' | 'missing' | 'superseded' | 'deleted' | 'invalid' | 'unknown'

/** Integrity claim on an artifact (`IntegrityStatus`). */
export type IntegrityStatus = 'verified' | 'unverified' | 'mismatch' | 'missing'

/** Trace completeness (`ProvenanceStatus`). */
export type ProvenanceStatus = 'complete' | 'incomplete' | 'unknown' | 'conflict'

/** Lineage completeness (`LineageCompleteness`). */
export type LineageCompleteness = 'complete' | 'partial' | 'unknown'

/**
 * Evidence-backed exposure classification (`ImpactStatus`). A viewer must
 * render these four states as four distinct claims; mapping
 * `unknown_incomplete_lineage` onto a not-affected stance is prohibited.
 */
export type ImpactStatus =
  | 'confirmed_exposed'
  | 'potentially_affected'
  | 'not_exposed_based_on_recorded_lineage'
  | 'unknown_incomplete_lineage'

/** One recorded artifact (`Artifact`). */
export interface Artifact {
  artifact_id: string
  run_id: string
  artifact_type: ArtifactType
  artifact_path: string
  artifact_hash: string | null
  artifact_version: string | null
  artifact_status: ArtifactStatus
  artifact_created_at: ISODateTime
  parent_artifact_id: string | null
  checkpoint_id: string | null
  checkpoint_path: string | null
  policy_version: string | null
  trajectory_id: string | null
  experience_id: string | null
  policy_update_id: string | null
  environment_id: string | null
  environment_version: string | null
  agent_config_fingerprint: string | null
  episode_id: string | null
  timestep: number | null
  update_index: number | null
  included_state_components: string[]
  integrity_status: IntegrityStatus
  metadata_schema_version: string
  metadata: Record<string, unknown>
  created_at: ISODateTime
  updated_at: ISODateTime
}

/** A recorded lineage link (`ArtifactLink`). */
export interface ArtifactLink {
  link_id: string
  run_id: string
  from_artifact_id: string
  to_artifact_id: string
  relation: string
  created_at: ISODateTime
}

/** Full run trace (`ProvenanceTrace`). */
export interface ProvenanceTrace {
  provenance_id: string
  run_id: string
  provenance_status: ProvenanceStatus
  lineage_completeness: LineageCompleteness
  source_environment_version: string | null
  environment_id: string | null
  environment_version: string | null
  artifact_count: number
  artifacts: Artifact[]
  links: ArtifactLink[]
  warnings: string[]
  evidence_ids: string[]
  details: Record<string, unknown>
  created_at: ISODateTime
  updated_at: ISODateTime
}

/** Artifact listing response (`RunArtifactList`). */
export interface RunArtifactList {
  run_id: string
  count: number
  artifacts: Artifact[]
}

/** Evidence-backed incident impact (`ImpactAnalysis`). */
export interface ImpactAnalysis {
  impact_id: string
  incident_id: string
  run_id: string
  impact_status: ImpactStatus
  impact_score: number | null
  source_environment_version: string | null
  corruption_start_timestep: number | null
  corruption_end_timestep: number | null
  affected_artifact_ids: string[]
  affected_trajectory_ids: string[]
  affected_policy_update_ids: string[]
  affected_checkpoint_ids: string[]
  evidence_ids: string[]
  warnings: string[]
  errors: string[]
  details: Record<string, unknown>
  created_at: ISODateTime
  completed_at: ISODateTime | null
}
