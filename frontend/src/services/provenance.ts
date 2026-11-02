/**
 * Provenance service — LIVE Person 4 endpoints.
 *
 * Binds the mounted `provenance.p4_router` (`backend/api/routers/provenance.py`):
 * - `GET /api/v1/runs/{run_id}/provenance`      -> ProvenanceTrace
 * - `GET /api/v1/runs/{run_id}/artifacts`       -> RunArtifactList
 * - `GET /api/v1/artifacts/{artifact_id}`       -> Artifact
 * - `GET /api/v1/incidents/{incident_id}/impact` -> ImpactAnalysis
 *
 * All reads; no destructive operations, so retries are always safe. Response
 * shapes are the canonical backend models — nothing is normalized into a
 * friendlier lie, and unknown lineage stays unknown in the UI.
 */
import type {
  Artifact,
  ImpactAnalysis,
  ProvenanceTrace,
  RunArtifactList,
} from '../schemas/provenance'
import type { ServiceResult } from './types'
import { api } from './client'

export function runProvenancePath(runId: string): string {
  return `/api/v1/runs/${encodeURIComponent(runId)}/provenance`
}

export function runArtifactsPath(runId: string): string {
  return `/api/v1/runs/${encodeURIComponent(runId)}/artifacts`
}

export function artifactPath(artifactId: string): string {
  return `/api/v1/artifacts/${encodeURIComponent(artifactId)}`
}

export function incidentImpactPath(incidentId: string): string {
  return `/api/v1/incidents/${encodeURIComponent(incidentId)}/impact`
}

export interface ProvenanceService {
  getRunProvenance(runId: string): Promise<ServiceResult<ProvenanceTrace>>
  listRunArtifacts(runId: string): Promise<ServiceResult<RunArtifactList>>
  getArtifact(artifactId: string): Promise<ServiceResult<Artifact>>
  getIncidentImpact(incidentId: string): Promise<ServiceResult<ImpactAnalysis>>
}

/** Real-mode adapter against the live provenance endpoints. */
const realAdapter: ProvenanceService = {
  getRunProvenance(runId) {
    return api.get<ProvenanceTrace>(runProvenancePath(runId))
  },
  listRunArtifacts(runId) {
    return api.get<RunArtifactList>(runArtifactsPath(runId))
  },
  getArtifact(artifactId) {
    return api.get<Artifact>(artifactPath(artifactId))
  },
  getIncidentImpact(incidentId) {
    return api.get<ImpactAnalysis>(incidentImpactPath(incidentId))
  },
}

/** Select the provenance adapter. Currently only the real adapter exists. */
export function createProvenanceService(): ProvenanceService {
  return realAdapter
}
