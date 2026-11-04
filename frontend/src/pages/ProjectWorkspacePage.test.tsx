import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ActiveProjectProvider, useActiveProject } from '../contexts/ActiveProjectContext'
import { ThemeProvider } from '../contexts/ThemeContext'
import {
  PID,
  failure,
  fakeService,
  intentResult,
  project,
  requirement,
  run,
  verifyResult,
} from '../features/projects/projectFixtures'
import type { ProjectService } from '../services/projects'
import { ProjectWorkspacePage } from './ProjectWorkspacePage'

function Probe() {
  const { activeProjectId } = useActiveProject()
  return <span data-testid="active">{activeProjectId ?? 'none'}</span>
}

function renderPage(service: ProjectService, path = `/projects/${PID}`) {
  return render(
    <ThemeProvider>
      <ActiveProjectProvider>
        <MemoryRouter initialEntries={[path]}>
          <Probe />
          <Routes>
            <Route
              path="/projects/:projectId"
              element={<ProjectWorkspacePage service={service} />}
            />
            <Route path="/projects" element={<div data-testid="dashboard" />} />
            <Route path="/studio" element={<div data-testid="studio" />} />
          </Routes>
        </MemoryRouter>
      </ActiveProjectProvider>
    </ThemeProvider>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(project()), { status: 200 })),
  )
})
afterEach(() => vi.unstubAllGlobals())

describe('ProjectWorkspacePage', () => {
  it('makes the opened project the active context, including via a direct link', async () => {
    renderPage(fakeService())
    expect(await screen.findByRole('heading', { name: 'Alpha' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('active')).toHaveTextContent(PID))
    expect(window.localStorage.getItem('rl-studio.activeProject')).toBe(PID)
  })

  it('shows only the project runs and an honest note when training has not started', async () => {
    renderPage(fakeService())
    expect(await screen.findByText(/Training has not started/)).toBeInTheDocument()
    expect(screen.getByText('Training not started')).toBeInTheDocument()
  })

  it('lists the runs of this project with status and counts', async () => {
    renderPage(
      fakeService({ listRuns: vi.fn(async () => ({ state: 'ok' as const, data: [run()] })) }),
    )
    const runs = await screen.findByRole('region', { name: 'Training runs' })
    expect(within(runs).getByText('ses_00000001_r1')).toBeInTheDocument()
    expect(within(runs).getByText(/12 episodes · 2048 steps/)).toBeInTheDocument()
  })

  it('shows not found, clears the active project and offers a way back', async () => {
    window.localStorage.setItem('rl-studio.activeProject', PID)
    renderPage(
      fakeService({
        getProject: vi.fn(() =>
          failure('not_found', 404),
        ) as unknown as ProjectService['getProject'],
      }),
    )
    expect(await screen.findByText('Project not found')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('active')).toHaveTextContent('none'))
    expect(screen.getByRole('link', { name: 'Back to projects' })).toHaveAttribute(
      'href',
      '/projects',
    )
  })

  it('opens Studio from the project', async () => {
    renderPage(fakeService())
    fireEvent.click(await screen.findByRole('button', { name: 'Open in Studio' }))
    expect(await screen.findByTestId('studio')).toBeInTheDocument()
  })
})

describe('Intent & Verification: before training', () => {
  it('submits expectations with no run, shows them as saved and waiting for evidence, and can confirm them', async () => {
    const proposed = requirement()
    const listRequirements = vi
      .fn()
      .mockResolvedValueOnce({ state: 'ok', data: [] })
      .mockResolvedValue({ state: 'ok', data: [proposed] })
    const service = fakeService({
      listRequirements,
      submitIntent: vi.fn(async () => ({ state: 'ok' as const, data: intentResult([proposed]) })),
    })
    renderPage(service)

    const box = await screen.findByLabelText('Expectations')
    expect(screen.getByText('Before training')).toBeInTheDocument()
    fireEvent.change(box, { target: { value: 'The final episode reward must be at least 1.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Interpret expectations' }))
    await waitFor(() =>
      expect(service.submitIntent).toHaveBeenCalledWith(PID, {
        statement: 'The final episode reward must be at least 1.',
      }),
    )

    const list = await screen.findByRole('list', { name: 'Project requirements' })
    expect(within(list).getByText('Proposed')).toBeInTheDocument()
    expect(
      within(list).getByText(/can only be verified once a run provides evidence/),
    ).toBeInTheDocument()

    fireEvent.click(within(list).getByRole('button', { name: 'Confirm' }))
    await waitFor(() =>
      expect(service.confirmRequirement).toHaveBeenCalledWith(PID, 'req_1', undefined),
    )
  })

  it('cannot verify without a run and says why, instead of inventing a result', async () => {
    renderPage(fakeService())
    expect(await screen.findByText(/No training run yet/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Verify run' })).not.toBeInTheDocument()
  })

  it('asks for a missing detail and sends it as an explicit override', async () => {
    const vague = requirement({
      lifecycle_status: 'needs_clarification',
      clarification_question: 'What reward counts as good?',
      expected_value: null,
      comparison_operator: null,
    })
    const service = fakeService({
      listRequirements: vi.fn(async () => ({ state: 'ok' as const, data: [vague] })),
    })
    renderPage(service)
    expect(await screen.findByText(/What reward counts as good\?/)).toBeInTheDocument()
    const confirm = screen.getByRole('button', { name: 'Confirm' })
    expect(confirm).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Expected value'), { target: { value: '5' } })
    fireEvent.click(confirm)
    await waitFor(() =>
      expect(service.confirmRequirement).toHaveBeenCalledWith(PID, 'req_1', {
        comparison_operator: '>=',
        expected_value: 5,
      }),
    )
  })

  it('reports an AI outage without implying anything was confirmed', async () => {
    const outage = intentResult([])
    outage.intents[0].ai = { error: { code: 'AI-009', message: 'down' } }
    renderPage(
      fakeService({ submitIntent: vi.fn(async () => ({ state: 'ok' as const, data: outage })) }),
    )
    fireEvent.change(await screen.findByLabelText('Expectations'), {
      target: { value: 'reward at least 5' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Interpret expectations' }))
    expect(await screen.findByText(/hosted AI was unavailable/)).toHaveTextContent(
      'nothing was confirmed or invented',
    )
  })

  it('uploads a document and uses it for interpretation', async () => {
    const doc = {
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
    }
    const listDocuments = vi
      .fn()
      .mockResolvedValueOnce({ state: 'ok', data: [] })
      .mockResolvedValue({ state: 'ok', data: [doc] })
    const service = fakeService({ listDocuments })
    renderPage(service)
    const input = await screen.findByLabelText('Requirements document')
    fireEvent.change(input, {
      target: { files: [new File(['# goals'], 'README.md', { type: 'text/markdown' })] },
    })
    await screen.findByRole('list', { name: 'Uploaded documents' })
    fireEvent.click(screen.getByRole('button', { name: 'Interpret expectations' }))
    await waitFor(() =>
      expect(service.submitIntent).toHaveBeenCalledWith(PID, { document_ids: ['doc_1'] }),
    )
  })

  it('flags contradictory requirements and blocks nothing silently', async () => {
    const a = requirement({ conflicts_with: ['req_2'] })
    renderPage(
      fakeService({ listRequirements: vi.fn(async () => ({ state: 'ok' as const, data: [a] })) }),
    )
    expect(await screen.findByText(/Contradicts another requirement/)).toBeInTheDocument()
  })
})

describe('Intent & Verification: during and after training', () => {
  const confirmed = requirement({
    lifecycle_status: 'confirmed',
    confirmation_status: 'confirmed',
    awaiting_run_evidence: false,
  })

  it('relates new expectations to an active run and labels the moment', async () => {
    const active = run({ status: 'running' })
    const service = fakeService({
      listRuns: vi.fn(async () => ({ state: 'ok' as const, data: [active] })),
      listRequirements: vi.fn(async () => ({ state: 'ok' as const, data: [confirmed] })),
    })
    renderPage(service)
    fireEvent.change(await screen.findByLabelText('Relates to run (optional)'), {
      target: { value: active.run_id },
    })
    expect(screen.getAllByText('During training').length).toBeGreaterThan(0)
    fireEvent.change(screen.getByLabelText('Expectations'), {
      target: { value: 'reward at least 7' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Interpret expectations' }))
    await waitFor(() =>
      expect(service.submitIntent).toHaveBeenCalledWith(PID, {
        statement: 'reward at least 7',
        run_id: active.run_id,
      }),
    )
  })

  it('verifies an active run as interim and says training is unaffected', async () => {
    const active = run({ status: 'running' })
    const verify = vi.fn(async () => ({
      state: 'ok' as const,
      data: verifyResult({ stage: 'during_training', interim: true, run_id: active.run_id }),
    }))
    renderPage(
      fakeService({
        listRuns: vi.fn(async () => ({ state: 'ok' as const, data: [active] })),
        listRequirements: vi.fn(async () => ({ state: 'ok' as const, data: [confirmed] })),
        verify,
      }),
    )
    fireEvent.change(await screen.findByLabelText('Run'), { target: { value: active.run_id } })
    expect(screen.getByText(/still training/)).toHaveTextContent('training is not affected')
    fireEvent.click(screen.getByRole('button', { name: 'Verify progress so far' }))
    await waitFor(() => expect(verify).toHaveBeenCalledWith(PID, { run_id: active.run_id }))
    expect(await screen.findByText('Interim result — run still training')).toBeInTheDocument()
  })

  it('shows "waiting for evidence" without recording or inventing a result', async () => {
    const active = run({ status: 'running', episode_count: 0 })
    renderPage(
      fakeService({
        listRuns: vi.fn(async () => ({ state: 'ok' as const, data: [active] })),
        listRequirements: vi.fn(async () => ({ state: 'ok' as const, data: [confirmed] })),
        verify: vi.fn(async () => ({
          state: 'ok' as const,
          data: verifyResult({
            state: 'waiting_for_evidence',
            verification: null,
            reason: 'no episode yet.',
          }),
        })),
      }),
    )
    fireEvent.change(await screen.findByLabelText('Run'), { target: { value: active.run_id } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify progress so far' }))
    expect(await screen.findByText(/Waiting for evidence/)).toHaveTextContent(
      'no result was recorded',
    )
  })

  it('shows the completed result with PASS/FAIL status, evidence and the incident link', async () => {
    renderPage(
      fakeService({
        listRuns: vi.fn(async () => ({ state: 'ok' as const, data: [run()] })),
        listRequirements: vi.fn(async () => ({ state: 'ok' as const, data: [confirmed] })),
      }),
    )
    fireEvent.change(await screen.findByLabelText('Run'), { target: { value: 'ses_00000001_r1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify run' }))
    expect(await screen.findByText('Completed result')).toBeInTheDocument()
    expect(screen.getByText('Overall: FAIL')).toBeInTheDocument()
    const results = screen.getByRole('list', { name: 'Requirement results' })
    expect(within(results).getByText('FAIL')).toBeInTheDocument()
    expect(within(results).getByText(/2 evidence reference\(s\)/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'open the incident' })).toHaveAttribute(
      'href',
      '/diagnosis-recovery?incidentId=inc_9',
    )
  })

  it('does not offer verification until a requirement is confirmed', async () => {
    renderPage(
      fakeService({ listRuns: vi.fn(async () => ({ state: 'ok' as const, data: [run()] })) }),
    )
    fireEvent.change(await screen.findByLabelText('Run'), { target: { value: 'ses_00000001_r1' } })
    expect(screen.getByRole('button', { name: 'Verify run' })).toBeDisabled()
  })

  it('explains a refused verification', async () => {
    renderPage(
      fakeService({
        listRuns: vi.fn(async () => ({ state: 'ok' as const, data: [run()] })),
        listRequirements: vi.fn(async () => ({ state: 'ok' as const, data: [confirmed] })),
        verify: vi.fn(() => failure('conflict', 409)) as unknown as ProjectService['verify'],
      }),
    )
    fireEvent.change(await screen.findByLabelText('Run'), { target: { value: 'ses_00000001_r1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Verify run' }))
    expect(await screen.findByText(/Nothing can be verified yet/)).toBeInTheDocument()
  })

  it('keeps an append-only history of verifications', async () => {
    const row = {
      project_id: PID,
      run_id: 'ses_00000001_r1',
      verification_id: 'ver_1',
      requirement_id: 'req_1',
      requirement_revision: 1,
      evaluation_status: 'fail',
      stage: 'post_training',
      run_status: 'completed',
      evidence_references: ['ev'],
      evaluation_window: {},
      created_at: '2026-11-02T11:00:00Z',
    }
    renderPage(
      fakeService({
        listVerifications: vi.fn(async () => ({ state: 'ok' as const, data: [row] })),
      }),
    )
    const history = await screen.findByRole('list', { name: 'Verification history' })
    expect(within(history).getByText('FAIL · rev 1')).toBeInTheDocument()
    expect(within(history).getByText('After training')).toBeInTheDocument()
  })
})
