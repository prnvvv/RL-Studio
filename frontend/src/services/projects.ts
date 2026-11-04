/**
 * Projects service: project CRUD, intent documents, project-level requirements and verification against runs.
 *
 * Binds `backend/api/routers/projects.py`. Every call resolves a `ServiceResult`; nothing here invents a project,
 * requirement or verification result when the backend is unreachable.
 */
import type {
  DocumentUploadResult,
  IntentSubmitRequest,
  IntentSubmitResult,
  ProjectCreateRequest,
  ProjectDocument,
  ProjectRequirement,
  ProjectRun,
  ProjectSummary,
  ProjectUpdateRequest,
  ProjectVerificationRow,
  RunVerificationView,
  VerifyResult,
} from '../schemas/projects'
import { buildRequestUrl, kindForStatus, MESSAGES, api } from './client'
import type { ServiceResult } from './types'
import { serviceError } from './types'

const BASE = '/api/v1/projects'
const UNEXPECTED = 'The service returned an unexpected response.'
const UPLOAD_TIMEOUT_MS = 60_000

const seg = encodeURIComponent

export interface VerifyRequest {
  run_id: string
  requirement_ids?: string[]
}

export interface ProjectService {
  listProjects(signal?: AbortSignal): Promise<ServiceResult<ProjectSummary[]>>
  getProject(projectId: string, signal?: AbortSignal): Promise<ServiceResult<ProjectSummary>>
  createProject(
    request: ProjectCreateRequest,
  ): Promise<ServiceResult<ProjectSummary & { intent?: unknown }>>
  updateProject(
    projectId: string,
    patch: ProjectUpdateRequest,
  ): Promise<ServiceResult<ProjectSummary>>
  /** `confirmName` must equal the project's name; the backend hides the project but deletes no data. */
  deleteProject(projectId: string, confirmName: string): Promise<ServiceResult<{ status: string }>>
  uploadDocument(
    projectId: string,
    file: File,
    signal?: AbortSignal,
  ): Promise<ServiceResult<DocumentUploadResult>>
  listDocuments(projectId: string, signal?: AbortSignal): Promise<ServiceResult<ProjectDocument[]>>
  submitIntent(
    projectId: string,
    request: IntentSubmitRequest,
  ): Promise<ServiceResult<IntentSubmitResult>>
  listRequirements(
    projectId: string,
    signal?: AbortSignal,
  ): Promise<ServiceResult<ProjectRequirement[]>>
  confirmRequirement(
    projectId: string,
    requirementId: string,
    overrides?: Record<string, unknown>,
  ): Promise<ServiceResult<ProjectRequirement>>
  rejectRequirement(
    projectId: string,
    requirementId: string,
    reason?: string,
  ): Promise<ServiceResult<ProjectRequirement>>
  listRuns(projectId: string, signal?: AbortSignal): Promise<ServiceResult<ProjectRun[]>>
  verify(projectId: string, request: VerifyRequest): Promise<ServiceResult<VerifyResult>>
  listVerifications(
    projectId: string,
    runId?: string,
    signal?: AbortSignal,
  ): Promise<ServiceResult<ProjectVerificationRow[]>>
  getVerification(
    projectId: string,
    verificationId: string,
    signal?: AbortSignal,
  ): Promise<ServiceResult<RunVerificationView>>
}

function unexpected<T>(): ServiceResult<T> {
  return serviceError('unexpected', UNEXPECTED)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Take a list out of `{ count, <key>: [...] }`; anything else is an unexpected response. */
function listOf<T>(data: unknown, key: string): ServiceResult<T[]> {
  if (!isRecord(data) || !Array.isArray(data[key])) return unexpected<T[]>()
  return { state: 'ok', data: data[key] as T[] }
}

function hasString(data: unknown, key: string): data is Record<string, unknown> {
  return isRecord(data) && typeof data[key] === 'string'
}

async function mapped<T>(
  promise: Promise<ServiceResult<unknown>>,
  check: (data: unknown) => ServiceResult<T>,
): Promise<ServiceResult<T>> {
  const result = await promise
  if (result.state === 'error') return result
  return check(result.data)
}

function expectProject(data: unknown): ServiceResult<ProjectSummary> {
  return hasString(data, 'project_id')
    ? { state: 'ok', data: data as unknown as ProjectSummary }
    : unexpected()
}

function expectRequirement(data: unknown): ServiceResult<ProjectRequirement> {
  return hasString(data, 'requirement_id')
    ? { state: 'ok', data: data as unknown as ProjectRequirement }
    : unexpected()
}

export function createProjectService(): ProjectService {
  return {
    listProjects: (signal) =>
      mapped(api.get<unknown>(BASE, { signal }), (d) => listOf<ProjectSummary>(d, 'projects')),

    getProject: (id, signal) =>
      mapped(api.get<unknown>(`${BASE}/${seg(id)}`, { signal }), expectProject),

    createProject: (request) =>
      mapped(api.post<unknown>(BASE, { jsonBody: request }), (d) =>
        hasString(d, 'project_id')
          ? { state: 'ok', data: d as unknown as ProjectSummary & { intent?: unknown } }
          : unexpected(),
      ),

    updateProject: (id, patch) =>
      mapped(
        api.request<unknown>(`${BASE}/${seg(id)}`, { method: 'PATCH', jsonBody: patch }),
        expectProject,
      ),

    deleteProject: (id, confirmName) =>
      mapped(
        api.request<unknown>(`${BASE}/${seg(id)}`, {
          method: 'DELETE',
          jsonBody: { confirm_name: confirmName },
        }),
        (d) =>
          hasString(d, 'status')
            ? { state: 'ok', data: { status: d.status as string } }
            : unexpected(),
      ),

    async uploadDocument(id, file, signal) {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS)
      const onAbort = () => controller.abort()
      signal?.addEventListener('abort', onAbort)
      try {
        const response = await fetch(
          buildRequestUrl(
            (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, ''),
            `${BASE}/${seg(id)}/documents?filename=${seg(file.name)}`,
          ),
          {
            method: 'POST',
            headers: {
              'Content-Type': file.type || 'application/octet-stream',
              Accept: 'application/json',
            },
            body: file,
            signal: controller.signal,
          },
        )
        if (!response.ok) {
          const kind = kindForStatus(response.status)
          return {
            state: 'error',
            error: { kind, message: MESSAGES[kind], status: response.status },
          }
        }
        const data: unknown = await response.json()
        if (!isRecord(data) || !isRecord(data.document)) return unexpected()
        return { state: 'ok', data: data as unknown as DocumentUploadResult }
      } catch (cause) {
        if (cause instanceof DOMException && cause.name === 'AbortError') {
          return serviceError('cancelled', MESSAGES.cancelled)
        }
        return serviceError('network', MESSAGES.network)
      } finally {
        clearTimeout(timer)
        signal?.removeEventListener('abort', onAbort)
      }
    },

    listDocuments: (id, signal) =>
      mapped(api.get<unknown>(`${BASE}/${seg(id)}/documents`, { signal }), (d) =>
        listOf<ProjectDocument>(d, 'documents'),
      ),

    submitIntent: (id, request) =>
      mapped(api.post<unknown>(`${BASE}/${seg(id)}/intents`, { jsonBody: request }), (d) =>
        isRecord(d) && Array.isArray(d.intents)
          ? { state: 'ok', data: d as unknown as IntentSubmitResult }
          : unexpected(),
      ),

    listRequirements: (id, signal) =>
      mapped(api.get<unknown>(`${BASE}/${seg(id)}/requirements`, { signal }), (d) =>
        listOf<ProjectRequirement>(d, 'requirements'),
      ),

    confirmRequirement: (id, rid, overrides) =>
      mapped(
        api.post<unknown>(`${BASE}/${seg(id)}/requirements/${seg(rid)}/confirm`, {
          jsonBody: overrides ? { overrides } : {},
        }),
        expectRequirement,
      ),

    rejectRequirement: (id, rid, reason) =>
      mapped(
        api.post<unknown>(`${BASE}/${seg(id)}/requirements/${seg(rid)}/reject`, {
          jsonBody: reason ? { reason } : {},
        }),
        expectRequirement,
      ),

    listRuns: (id, signal) =>
      mapped(api.get<unknown>(`${BASE}/${seg(id)}/runs`, { signal }), (d) =>
        listOf<ProjectRun>(d, 'runs'),
      ),

    verify: (id, request) =>
      mapped(api.post<unknown>(`${BASE}/${seg(id)}/verifications`, { jsonBody: request }), (d) =>
        isRecord(d) && (d.state === 'evaluated' || d.state === 'waiting_for_evidence')
          ? { state: 'ok', data: d as unknown as VerifyResult }
          : unexpected(),
      ),

    listVerifications: (id, runId, signal) =>
      mapped(
        api.get<unknown>(
          `${BASE}/${seg(id)}/verifications${runId ? `?run_id=${seg(runId)}` : ''}`,
          { signal },
        ),
        (d) => listOf<ProjectVerificationRow>(d, 'verifications'),
      ),

    getVerification: (id, vid, signal) =>
      mapped(api.get<unknown>(`${BASE}/${seg(id)}/verifications/${seg(vid)}`, { signal }), (d) =>
        hasString(d, 'verification_id')
          ? { state: 'ok', data: d as unknown as RunVerificationView }
          : unexpected(),
      ),
  }
}
