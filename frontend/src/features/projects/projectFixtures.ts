import { vi } from 'vitest'
import type {
  IntentSubmitResult,
  ProjectRequirement,
  ProjectRun,
  ProjectSummary,
  VerifyResult,
} from '../../schemas/projects'
import type { ProjectService } from '../../services/projects'

export const PID = 'prj_0123456789abcdef'

export function project(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
  return {
    project_id: PID,
    name: 'Alpha',
    description: null,
    status: 'active',
    created_at: '2026-11-01T10:00:00Z',
    updated_at: '2026-11-02T10:00:00Z',
    agent: {},
    environment: {},
    training: { state: 'not_started', run_count: 0, active_runs: 0, completed_runs: 0 },
    requirements: { total: 0, confirmed: 0, pending: 0 },
    last_verification: null,
    verification_count: 0,
    ...overrides,
  }
}

export function requirement(overrides: Partial<ProjectRequirement> = {}): ProjectRequirement {
  return {
    requirement_id: 'req_1',
    project_id: PID,
    requirement_key: 'req_1',
    requirement_revision: 1,
    supersedes: null,
    superseded: false,
    stage: 'pre_training',
    source: { type: 'text' },
    category: 'reward',
    source_statement: 'the final episode reward must be at least 1',
    description: 'final episode reward >= 1',
    comparison_operator: '>=',
    expected_value: 1,
    tolerance: null,
    lifecycle_status: 'draft',
    validation_status: 'not_evaluable',
    confirmation_status: 'proposed',
    clarification_question: null,
    validation: {},
    awaiting_run_evidence: true,
    conflicts_with: [],
    latest_verification: null,
    ...overrides,
  }
}

export function run(overrides: Partial<ProjectRun> = {}): ProjectRun {
  return {
    run_id: 'ses_00000001_r1',
    project_id: PID,
    status: 'completed',
    environment_id: 'cartpole',
    environment_version: 'CartPole-v1',
    agent: 'PPO',
    name: 'PPO on cartpole',
    episode_count: 12,
    step_count: 2048,
    created_at: '2026-11-02T10:00:00Z',
    finished_at: null,
    ...overrides,
  }
}

export function intentResult(reqs: ProjectRequirement[]): IntentSubmitResult {
  return {
    project_id: PID,
    stage: 'pre_training',
    run_id: null,
    requirement_count: reqs.length,
    intents: [
      {
        intent_id: 'int_1',
        status: 'interpreted',
        status_reason: null,
        original_text: 'x',
        stage: 'pre_training',
        source: { type: 'text' },
        requirements: reqs,
        ai: {},
      },
    ],
  }
}

export function verifyResult(overrides: Partial<VerifyResult> = {}): VerifyResult {
  return {
    project_id: PID,
    run_id: 'ses_00000001_r1',
    state: 'evaluated',
    stage: 'post_training',
    interim: false,
    evaluation_window: {},
    skipped: {},
    verification: {
      verification_id: 'ver_1',
      run_id: 'ses_00000001_r1',
      overall_status: 'fail',
      created_at: '2026-11-02T11:00:00Z',
      incident: { handoff_status: 'created', incident_id: 'inc_9', error_code: null },
      results: [
        {
          requirement_id: 'run_req_1',
          status: 'fail',
          source_statement: 'the final episode reward must be at least 100000',
          evidence_refs: ['ev1', 'ev2'],
          actual: 21,
        },
      ],
    },
    ...overrides,
  }
}

const ok = <T>(data: T) => Promise.resolve({ state: 'ok' as const, data })

/** A `ProjectService` whose every method resolves ok; override what a test cares about. */
export function fakeService(overrides: Partial<ProjectService> = {}): ProjectService {
  return {
    listProjects: vi.fn(() => ok([])),
    getProject: vi.fn(() => ok(project())),
    createProject: vi.fn(() => ok(project())),
    updateProject: vi.fn(() => ok(project())),
    deleteProject: vi.fn(() => ok({ status: 'deleted' })),
    uploadDocument: vi.fn(() =>
      ok({
        duplicate: false,
        document: {
          document_id: 'doc_1',
          project_id: PID,
          filename: 'README.md',
          content_type: 'text/markdown',
          size_bytes: 10,
          sha256: 'a',
          extraction_status: 'extracted' as const,
          extraction_error: null,
          text_chars: 10,
          preview: 'x',
          created_at: '2026-11-02T10:00:00Z',
        },
      }),
    ),
    listDocuments: vi.fn(() => ok([])),
    submitIntent: vi.fn(() => ok(intentResult([]))),
    listRequirements: vi.fn(() => ok([])),
    confirmRequirement: vi.fn(() =>
      ok(requirement({ lifecycle_status: 'confirmed', confirmation_status: 'confirmed' })),
    ),
    rejectRequirement: vi.fn(() =>
      ok(requirement({ lifecycle_status: 'rejected', confirmation_status: 'rejected' })),
    ),
    listRuns: vi.fn(() => ok([])),
    verify: vi.fn(() => ok(verifyResult())),
    listVerifications: vi.fn(() => ok([])),
    getVerification: vi.fn(() => ok(verifyResult().verification!)),
    ...overrides,
  }
}

export function failure(
  kind: 'not_found' | 'conflict' | 'network' | 'invalid_request',
  status?: number,
) {
  return Promise.resolve({
    state: 'error' as const,
    error: { kind, message: `${kind} message`, ...(status ? { status } : {}) },
  })
}
