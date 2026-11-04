import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ActiveProjectProvider } from '../contexts/ActiveProjectContext'
import { ThemeProvider } from '../contexts/ThemeContext'
import { PID, failure, fakeService, project } from '../features/projects/projectFixtures'
import type { ProjectService } from '../services/projects'
import { ProjectsPage } from './ProjectsPage'

vi.mock('../features/landing/AmbientWaves', () => ({
  AmbientWaves: () => <canvas data-testid="ambient-waves" />,
}))
vi.mock('../components/ui/background-ascii-wake', () => ({
  WakeGlyph: ({ className }: { className?: string }) => (
    <div data-testid="wake" className={className} />
  ),
}))

function lastCreateButton(): HTMLElement {
  const buttons = screen.getAllByRole('button', { name: 'Create project' })
  return buttons[buttons.length - 1]
}

function renderPage(service: ProjectService) {
  return render(
    <ThemeProvider>
      <ActiveProjectProvider>
        <MemoryRouter initialEntries={['/projects']}>
          <Routes>
            <Route path="/projects" element={<ProjectsPage service={service} />} />
            <Route path="/projects/:projectId" element={<div data-testid="workspace" />} />
          </Routes>
        </MemoryRouter>
      </ActiveProjectProvider>
    </ThemeProvider>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
  // The shared navigation shows the active project; nothing here needs a real backend.
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('{}', { status: 404 })),
  )
})
afterEach(() => vi.unstubAllGlobals())

describe('ProjectsPage', () => {
  it('uses the landing page background component, not a lookalike', async () => {
    renderPage(fakeService())
    await screen.findByText('No projects yet')
    expect(screen.getByTestId('wake')).toHaveClass('ls-wake')
    expect(screen.getByTestId('ambient-waves')).toBeInTheDocument()
    expect(document.querySelector('.ls-first-screen.pj-backdrop')).not.toBeNull()
    expect(document.querySelector('.ls-root')).not.toBeNull()
  })

  it('shows a loading state, then an empty state with a clear create action', async () => {
    let resolve: (v: unknown) => void = () => {}
    const listProjects = vi.fn(
      () => new Promise((r) => (resolve = r)),
    ) as unknown as ProjectService['listProjects']
    renderPage(fakeService({ listProjects }))
    expect(screen.getByText('Loading projects…')).toBeInTheDocument()
    resolve({ state: 'ok', data: [] })
    expect(await screen.findByText('No projects yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create your first project' })).toBeInTheDocument()
  })

  it('shows an error state with retry', async () => {
    const listProjects = vi
      .fn()
      .mockReturnValueOnce(failure('network'))
      .mockResolvedValue({ state: 'ok', data: [] })
    renderPage(fakeService({ listProjects }))
    expect(await screen.findByText('Projects could not be loaded')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('No projects yet')).toBeInTheDocument()
  })

  it('lists projects with training state, configuration, counts and timestamps', async () => {
    const started = project({
      name: 'Beta',
      agent: { agent: 'PPO' },
      environment: { environment: 'cartpole' },
      training: { state: 'active', run_count: 2, active_runs: 1, completed_runs: 1 },
      requirements: { total: 3, confirmed: 2, pending: 1 },
      last_verification: { run_id: 'ses_1_r1', status: 'fail', at: '2026-11-02T11:00:00Z' },
    })
    const fresh = project({ project_id: 'prj_aaaaaaaaaaaaaaaa', name: 'Gamma' })
    renderPage(
      fakeService({
        listProjects: vi.fn(async () => ({ state: 'ok' as const, data: [started, fresh] })),
      }),
    )

    const beta = await screen.findByRole('article', { name: 'Project Beta' })
    expect(within(beta).getByText('Training active')).toBeInTheDocument()
    expect(within(beta).getByText('Agent: PPO')).toBeInTheDocument()
    expect(within(beta).getByText('2 (1 active)')).toBeInTheDocument()
    expect(within(beta).getByText('2 confirmed, 1 pending')).toBeInTheDocument()
    expect(within(beta).getByText('FAIL on ses_1_r1')).toBeInTheDocument()

    const gamma = screen.getByRole('article', { name: 'Project Gamma' })
    expect(within(gamma).getByText('Training not started')).toBeInTheDocument()
    expect(within(gamma).getByText('Agent: not configured')).toBeInTheDocument()
    expect(within(gamma).getByText('None yet')).toBeInTheDocument()
  })

  it('opens a project: it becomes the active context and the workspace route loads', async () => {
    renderPage(
      fakeService({
        listProjects: vi.fn(async () => ({ state: 'ok' as const, data: [project()] })),
      }),
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Open project' }))
    expect(await screen.findByTestId('workspace')).toBeInTheDocument()
    expect(window.localStorage.getItem('rl-studio.activeProject')).toBe(PID)
  })

  it('renames a project in place and keeps its id', async () => {
    const updateProject = vi.fn(async () => ({
      state: 'ok' as const,
      data: project({ name: 'Renamed' }),
    }))
    renderPage(
      fakeService({
        listProjects: vi.fn(async () => ({ state: 'ok' as const, data: [project()] })),
        updateProject,
      }),
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Rename' }))
    const input = screen.getByLabelText('Project name')
    fireEvent.change(input, { target: { value: 'Renamed' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('heading', { name: 'Renamed' })).toBeInTheDocument()
    expect(updateProject).toHaveBeenCalledWith(PID, { name: 'Renamed' })
  })

  it('requires the exact name to delete, then refreshes the list', async () => {
    const deleteProject = vi.fn(async () => ({ state: 'ok' as const, data: { status: 'deleted' } }))
    const listProjects = vi
      .fn()
      .mockResolvedValueOnce({ state: 'ok', data: [project()] })
      .mockResolvedValue({ state: 'ok', data: [] })
    renderPage(fakeService({ listProjects, deleteProject }))
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    const confirm = screen.getByRole('button', { name: 'Delete project' })
    expect(confirm).toBeDisabled()
    expect(screen.getByText(/are kept and are not deleted/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Type the project name to confirm'), {
      target: { value: 'alpha' },
    })
    expect(confirm).toBeDisabled() // case matters
    fireEvent.change(screen.getByLabelText('Type the project name to confirm'), {
      target: { value: 'Alpha' },
    })
    expect(confirm).toBeEnabled()
    fireEvent.click(confirm)
    await waitFor(() => expect(deleteProject).toHaveBeenCalledWith(PID, 'Alpha'))
    expect(await screen.findByText('No projects yet')).toBeInTheDocument()
  })

  it('explains a refused delete (active training) and keeps the project', async () => {
    const deleteProject = vi.fn(() =>
      failure('conflict', 409),
    ) as unknown as ProjectService['deleteProject']
    renderPage(
      fakeService({
        listProjects: vi.fn(async () => ({ state: 'ok' as const, data: [project()] })),
        deleteProject,
      }),
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    fireEvent.change(screen.getByLabelText('Type the project name to confirm'), {
      target: { value: 'Alpha' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Delete project' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('stop its active training run first')
  })

  it('creates a project with only a name and opens it', async () => {
    const createProject = vi.fn(async () => ({ state: 'ok' as const, data: project() }))
    renderPage(fakeService({ createProject }))
    fireEvent.click(await screen.findByRole('button', { name: 'Create project' }))
    fireEvent.click(lastCreateButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter a project name.')
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Alpha' } })
    fireEvent.click(lastCreateButton())
    await waitFor(() => expect(createProject).toHaveBeenCalledWith({ name: 'Alpha' }))
    expect(await screen.findByTestId('workspace')).toBeInTheDocument()
  })

  it('creates a project with intent text and a document through the same pipeline', async () => {
    const createProject = vi.fn(async () => ({ state: 'ok' as const, data: project() }))
    const service = fakeService({ createProject })
    renderPage(service)
    fireEvent.click(await screen.findByRole('button', { name: 'Create project' }))
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Alpha' } })
    fireEvent.change(screen.getByLabelText(/What should the agent achieve/), {
      target: { value: 'reward >= 1' },
    })
    const file = new File(['# goals'], 'README.md', { type: 'text/markdown' })
    fireEvent.change(screen.getByLabelText(/Requirements document/), { target: { files: [file] } })
    fireEvent.click(lastCreateButton())
    await waitFor(() =>
      expect(service.submitIntent).toHaveBeenCalledWith(PID, { document_ids: ['doc_1'] }),
    )
    expect(createProject).toHaveBeenCalledWith({
      name: 'Alpha',
      intent: { statement: 'reward >= 1' },
    })
    expect(service.uploadDocument).toHaveBeenCalledWith(PID, file)
  })

  it('rejects an unsupported document before upload', async () => {
    const service = fakeService()
    renderPage(service)
    fireEvent.click(await screen.findByRole('button', { name: 'Create project' }))
    fireEvent.change(screen.getByLabelText('Project name'), { target: { value: 'Alpha' } })
    fireEvent.change(screen.getByLabelText(/Requirements document/), {
      target: { files: [new File(['x'], 'run.exe')] },
    })
    fireEvent.click(lastCreateButton())
    expect(await screen.findByRole('alert')).toHaveTextContent('Unsupported file type')
    expect(service.createProject).not.toHaveBeenCalled()
  })
})
