import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ActiveProjectProvider } from '../../contexts/ActiveProjectContext'
import { ThemeProvider } from '../../contexts/ThemeContext'
import { DiagnosisRecoveryPage } from '../../pages/DiagnosisRecoveryPage'
import { MonitoringPage } from '../../pages/MonitoringPage'
import { ProjectWorkspacePage } from '../../pages/ProjectWorkspacePage'
import { ReportsPage } from '../../pages/ReportsPage'
import { setProjectScope } from '../../services/projectScope'
import {
  PROJECT_A,
  PROJECT_B,
  activateProject,
  installHistoryFake,
  makeRun,
} from '../../test/trainingHistoryFake'
import { TrainingHistoryPanel } from './TrainingHistoryPanel'

/** Two finished runs of the same project. The NEWER one has very different numbers, so any mix-up is visible. */
const OLDER = makeRun({
  run_id: 'ses_00000001_r1',
  started_at: '2026-11-01T10:00:00+00:00',
  total_timesteps: 1000,
  total_episodes: 12,
  status: 'stopped',
  termination_reason: 'user_requested_stop',
  final_metrics: { mean_reward: 5, best_reward: 11 },
})
const NEWER = makeRun({
  run_id: 'ses_00000002_r1',
  started_at: '2026-11-02T10:00:00+00:00',
  total_timesteps: 9000,
  total_episodes: 99,
  status: 'completed',
  final_metrics: { mean_reward: 187.25, best_reward: 200 },
})

class QuietSocket {
  close = vi.fn()
  onopen = null
  onmessage = null
  onerror = null
  onclose = null
}

function Where() {
  const location = useLocation()
  return <output aria-label="location">{`${location.pathname}${location.search}`}</output>
}

function Navigator({ to }: { to: number | string }) {
  const navigate = useNavigate()
  return (
    <button type="button" onClick={() => navigate(to as never)}>
      go
    </button>
  )
}

function mount(entry: string, element: React.ReactNode, path = '/monitoring') {
  return render(
    <ThemeProvider>
      <ActiveProjectProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Where />
          <Navigator to={-1} />
          <Routes>
            <Route path={path} element={element} />
            <Route path="*" element={<p>elsewhere</p>} />
          </Routes>
        </MemoryRouter>
      </ActiveProjectProvider>
    </ThemeProvider>,
  )
}

/** A project service whose other reads (requirements, documents, verification history) simply return nothing. */
function permissive<T extends object>(base: T): T {
  return new Proxy(base, {
    get: (target, key) =>
      key in target
        ? (target as Record<PropertyKey, unknown>)[key]
        : async () => ({ state: 'ok', data: [] }),
  })
}

const bar = () => screen.getByRole('region', { name: 'Training run context' })
const where = () => screen.getByLabelText('location').textContent

beforeEach(() => {
  window.localStorage.clear()
  setProjectScope(null)
  vi.stubGlobal('WebSocket', QuietSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.localStorage.clear()
  setProjectScope(null)
})

describe('shared run context', () => {
  it('says there is no history to show when no project is open', async () => {
    installHistoryFake({ runs: [OLDER] })
    mount('/monitoring', <MonitoringPage />)
    expect(await screen.findByText(/No project is open/)).toBeInTheDocument()
    expect(where()).toBe('/monitoring')
  })

  it('resolves the project’s latest run automatically and writes it into the URL', async () => {
    activateProject(PROJECT_A)
    installHistoryFake({ runs: [OLDER, NEWER] })
    mount('/monitoring', <MonitoringPage />)
    await waitFor(() => expect(where()).toBe(`/monitoring?runId=${NEWER.run_id}`))
    expect(await within(bar()).findByRole('combobox')).toHaveValue(NEWER.run_id)
    expect(await within(bar()).findByText('completed')).toBeInTheDocument()
  })

  it('opens a deep link on exactly that run and lets the user switch runs without returning to Studio', async () => {
    activateProject(PROJECT_A)
    installHistoryFake({ runs: [OLDER, NEWER] })
    mount(`/monitoring?runId=${OLDER.run_id}`, <MonitoringPage />)
    const select = await within(bar()).findByRole('combobox')
    await waitFor(() => expect(select).toHaveValue(OLDER.run_id))
    expect(await within(bar()).findByText('Stopped by the user')).toBeInTheDocument()
    fireEvent.change(select, { target: { value: NEWER.run_id } })
    await waitFor(() => expect(where()).toBe(`/monitoring?runId=${NEWER.run_id}`))
    expect(await within(bar()).findByText('Completed naturally')).toBeInTheDocument()
  })

  it('supports browser back after switching run', async () => {
    activateProject(PROJECT_A)
    installHistoryFake({ runs: [OLDER, NEWER] })
    mount(`/monitoring?runId=${OLDER.run_id}`, <MonitoringPage />)
    const select = await within(bar()).findByRole('combobox')
    await waitFor(() => expect(select).toHaveValue(OLDER.run_id))
    fireEvent.change(select, { target: { value: NEWER.run_id } })
    await waitFor(() => expect(where()).toContain(NEWER.run_id))
    fireEvent.click(screen.getByRole('button', { name: 'go' })) // browser back
    await waitFor(() => expect(where()).toContain(OLDER.run_id))
    expect(await within(bar()).findByRole('combobox')).toHaveValue(OLDER.run_id)
  })

  it('restores the same run after a refresh (a fresh mount of the same URL)', async () => {
    activateProject(PROJECT_A)
    installHistoryFake({ runs: [OLDER, NEWER] })
    const first = mount(`/monitoring?runId=${OLDER.run_id}`, <MonitoringPage />)
    await within(bar()).findByText('Stopped by the user')
    first.unmount()
    mount(`/monitoring?runId=${OLDER.run_id}`, <MonitoringPage />)
    expect(await within(bar()).findByText('Stopped by the user')).toBeInTheDocument()
  })

  it('uses the run last selected in this project when the URL names none', async () => {
    activateProject(PROJECT_A)
    window.localStorage.setItem(`rl-studio.selectedRun.${PROJECT_A}`, OLDER.run_id)
    installHistoryFake({ runs: [OLDER, NEWER] })
    mount('/monitoring', <MonitoringPage />)
    await waitFor(() => expect(where()).toBe(`/monitoring?runId=${OLDER.run_id}`))
  })

  it('shows a clear message and a way out for a run id that is not in this project', async () => {
    activateProject(PROJECT_A)
    installHistoryFake({ runs: [OLDER, NEWER] })
    mount('/monitoring?runId=ses_deadbeef_r1', <MonitoringPage />)
    expect(await within(bar()).findByRole('alert')).toHaveTextContent(
      'is not available in this project',
    )
    fireEvent.click(within(bar()).getByRole('button', { name: 'Use the latest run' }))
    await waitFor(() => expect(where()).toBe(`/monitoring?runId=${NEWER.run_id}`))
  })

  it('never serves another project’s run: a project A run id opened in project B is invalid', async () => {
    activateProject(PROJECT_B)
    installHistoryFake({
      runs: [
        OLDER,
        NEWER,
        makeRun({ run_id: 'ses_0000000b_r1', project_id: PROJECT_B, agent_name: 'DQN' }),
      ],
    })
    mount(`/monitoring?runId=${NEWER.run_id}`, <MonitoringPage />)
    expect(await within(bar()).findByRole('alert')).toHaveTextContent(
      'is not available in this project',
    )
    expect(screen.queryByText('187.25')).not.toBeInTheDocument()
  })

  it('invites the user to train when the project has no runs', async () => {
    activateProject(PROJECT_A)
    installHistoryFake({ runs: [] })
    mount('/monitoring', <MonitoringPage />)
    expect(await screen.findByText(/No training runs yet in this project/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Train an agent in Studio/ })).toHaveAttribute(
      'href',
      '/studio?view=training',
    )
  })
})

describe('Monitoring shows the selected run’s persisted data', () => {
  it('loads a stopped run’s recorded metrics instead of expecting a live process', async () => {
    activateProject(PROJECT_A)
    installHistoryFake({
      runs: [OLDER, NEWER],
      metrics: {
        [OLDER.run_id]: {
          episodes: [
            { episode: 1, reward: 4, end_step: 50 },
            { episode: 2, reward: 6, end_step: 120 },
          ],
        },
      },
    })
    mount(`/monitoring?runId=${OLDER.run_id}`, <MonitoringPage />)
    const stats = await screen.findByRole('region', { name: 'Live Stats' })
    await waitFor(() => expect(within(stats).getByText('5.00')).toBeInTheDocument()) // OLDER mean reward
    expect(within(stats).getByText('1000')).toBeInTheDocument() // OLDER timesteps
    expect(within(stats).queryByText('187.25')).not.toBeInTheDocument() // never the newest run's numbers
    expect(within(stats).getByText(/persisted training record/)).toBeInTheDocument()
    expect(screen.getByText(/Episode rewards recorded for ses_00000001_r1/)).toBeInTheDocument()
    const lifecycle = screen.getByRole('region', { name: 'Run lifecycle' })
    expect(within(lifecycle).getByText('Stopped by the user')).toBeInTheDocument()
  })

  it('reloads the right data when the run changes', async () => {
    activateProject(PROJECT_A)
    installHistoryFake({ runs: [OLDER, NEWER] })
    mount(`/monitoring?runId=${OLDER.run_id}`, <MonitoringPage />)
    const stats = await screen.findByRole('region', { name: 'Live Stats' })
    await waitFor(() => expect(within(stats).getByText('5.00')).toBeInTheDocument())
    fireEvent.change(within(bar()).getByRole('combobox'), { target: { value: NEWER.run_id } })
    await waitFor(() => expect(within(stats).getByText('187.25')).toBeInTheDocument())
    expect(within(stats).queryByText('5.00')).not.toBeInTheDocument()
  })

  it('leaves a value the run never recorded unavailable (no invented zero)', async () => {
    activateProject(PROJECT_A)
    const bare = makeRun({
      run_id: 'ses_0000000c_r1',
      final_metrics: {},
      total_episodes: 0,
      total_timesteps: 0,
      status: 'interrupted',
      termination_reason: 'unexpected_interruption',
    })
    installHistoryFake({ runs: [bare] })
    mount(`/monitoring?runId=${bare.run_id}`, <MonitoringPage />)
    const stats = await screen.findByRole('region', { name: 'Live Stats' })
    await waitFor(() =>
      expect(within(stats).getAllByText('Not available').length).toBeGreaterThanOrEqual(2),
    )
    expect(within(stats).queryByText('0.00')).not.toBeInTheDocument()
    expect(
      (await screen.findAllByText('Interrupted (the backend stopped)')).length,
    ).toBeGreaterThan(0)
  })
})

describe('Reports are built from the selected run only', () => {
  it('lists the project’s runs and reports the older run without the newest run’s numbers', async () => {
    activateProject(PROJECT_A)
    installHistoryFake({
      runs: [OLDER, NEWER],
      details: {
        [OLDER.run_id]: {
          verifications: [
            {
              verification_id: 'ver_1',
              overall_status: 'fail',
              created_at: '2026-11-01T11:00:00+00:00',
            },
          ],
        },
      },
    })
    mount(`/reports?runId=${OLDER.run_id}`, <ReportsPage />, '/reports')
    const table = await screen.findByRole('table')
    await waitFor(() => expect(within(table).getByText(NEWER.run_id)).toBeInTheDocument())
    expect(within(table).getByText(OLDER.run_id)).toBeInTheDocument()
    expect(within(table).getAllByText('PPO v1', { exact: false })).toHaveLength(2)
    const report = await screen.findByLabelText(`Report for run ${OLDER.run_id}`)
    expect(within(report).getByText('Stopped by the user')).toBeInTheDocument()
    expect(within(report).getByText('1000')).toBeInTheDocument()
    expect(within(report).getByText('5.00')).toBeInTheDocument()
    expect(within(report).getByText('0.0003')).toBeInTheDocument() // this run's own snapshot
    expect(within(report).queryByText('187.25')).not.toBeInTheDocument()
    expect(within(report).getByText(/ver_1 \(fail\)/)).toBeInTheDocument()
    expect(within(report).getByText('No incidents were recorded for this run.')).toBeInTheDocument()
  })

  it('marks a report for a run that is still training as a partial snapshot', async () => {
    activateProject(PROJECT_A)
    const live = makeRun({
      run_id: 'ses_0000000d_r1',
      status: 'running',
      active: true,
      finished_at: null,
      termination_reason: null,
    })
    installHistoryFake({ runs: [live] })
    mount(`/reports?runId=${live.run_id}`, <ReportsPage />, '/reports')
    expect(
      await screen.findByText(/still in progress, so the report below is a partial snapshot/),
    ).toBeInTheDocument()
  })
})

describe('Diagnosis follows the selected run', () => {
  it('lists only this run’s incidents and links them with the run kept in the URL', async () => {
    activateProject(PROJECT_A)
    installHistoryFake({
      runs: [OLDER, NEWER],
      details: {
        [NEWER.run_id]: {
          incidents: [
            {
              incident_id: 'inc_1',
              status: 'detected',
              severity: 'high',
              summary: 'reward collapsed',
              created_at: '2026-11-02T11:00:00+00:00',
              investigations: 2,
            },
          ],
          recoveries: [
            {
              recovery_id: 'rec_1',
              incident_id: 'inc_1',
              recovery_status: 'completed',
              recovery_strategy: 'restore_checkpoint',
              created_at: '2026-11-02T12:00:00+00:00',
            },
          ],
        },
      },
    })
    mount(
      `/diagnosis-recovery?runId=${NEWER.run_id}`,
      <DiagnosisRecoveryPage />,
      '/diagnosis-recovery',
    )
    const panel = await screen.findByRole('region', { name: 'Incidents recorded for this run' })
    const link = await within(panel).findByRole('link', { name: 'inc_1' })
    expect(link).toHaveAttribute(
      'href',
      `/diagnosis-recovery?runId=${NEWER.run_id}&incidentId=inc_1`,
    )
    expect(within(panel).getByText(/2 investigations/)).toBeInTheDocument()
    expect(
      within(panel).getByText(/rec_1 \(restore_checkpoint, completed\) for inc_1/),
    ).toBeInTheDocument()
  })

  it('shows an empty state, not a manufactured incident, for a run without incidents', async () => {
    activateProject(PROJECT_A)
    installHistoryFake({ runs: [OLDER] })
    mount(
      `/diagnosis-recovery?runId=${OLDER.run_id}`,
      <DiagnosisRecoveryPage />,
      '/diagnosis-recovery',
    )
    const panel = await screen.findByRole('region', { name: 'Incidents recorded for this run' })
    expect(
      await within(panel).findByText(/No incident was recorded for this run/),
    ).toBeInTheDocument()
    expect(within(panel).queryByRole('link')).not.toBeInTheDocument()
  })

  it('warns when the focused incident is not an incident of the selected run', async () => {
    activateProject(PROJECT_A)
    installHistoryFake({ runs: [OLDER] })
    mount(
      `/diagnosis-recovery?runId=${OLDER.run_id}&incidentId=inc_other`,
      <DiagnosisRecoveryPage />,
      '/diagnosis-recovery',
    )
    expect(
      await screen.findByText('Incident inc_other is not an incident of this run.'),
    ).toBeInTheDocument()
  })
})

describe('Training history in the project workspace', () => {
  function workspace(entry: string) {
    const service = {
      getProject: vi.fn(async () => ({
        state: 'ok' as const,
        data: {
          project_id: PROJECT_A,
          name: 'Alpha',
          description: null,
          status: 'active',
          created_at: '2026-11-01T00:00:00+00:00',
          updated_at: '2026-11-01T00:00:00+00:00',
          agent: {},
          environment: {},
          training: { state: 'not_started' },
          counts: {},
        },
      })),
      listRuns: vi.fn(async () => ({ state: 'ok' as const, data: [] })),
    }
    return render(
      <ThemeProvider>
        <ActiveProjectProvider>
          <MemoryRouter initialEntries={[entry]}>
            <Routes>
              <Route
                path="/projects/:projectId"
                element={<ProjectWorkspacePage service={permissive(service) as never} />}
              />
            </Routes>
          </MemoryRouter>
        </ActiveProjectProvider>
      </ThemeProvider>,
    )
  }

  it('shows the whole history with per-run links into every page, carrying the run in the URL', async () => {
    installHistoryFake({ runs: [OLDER, NEWER] })
    workspace(`/projects/${PROJECT_A}`)
    const section = await screen.findByRole('region', { name: 'Training history' })
    const table = await within(section).findByRole('table')
    const row = within(table).getByText(OLDER.run_id).closest('tr') as HTMLElement
    const hrefs = within(row)
      .getAllByRole('link')
      .map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual([
      `/monitoring?runId=${OLDER.run_id}`,
      `/reports?runId=${OLDER.run_id}`,
      `/diagnosis-recovery?runId=${OLDER.run_id}`,
      `/projects/${PROJECT_A}?runId=${OLDER.run_id}#verification`,
    ])
  })
})

describe('TrainingHistoryPanel', () => {
  const call = (spy: ReturnType<typeof installHistoryFake>) =>
    spy.mock.calls.map((c) => String(c[0]))

  it('queries the backend for filters, search and paging instead of filtering a loaded page in the browser', async () => {
    const spy = installHistoryFake({
      runs: [
        OLDER,
        NEWER,
        makeRun({
          run_id: 'ses_0000000e_r1',
          agent_id: 'agt_000000000002',
          agent_name: 'A2C',
          started_at: '2026-11-03T10:00:00+00:00',
        }),
      ],
    })
    render(
      <MemoryRouter>
        <TrainingHistoryPanel projectId={PROJECT_A} />
      </MemoryRouter>,
    )
    await screen.findByText('ses_0000000e_r1')
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'stopped' } })
    await waitFor(() => expect(call(spy).some((u) => u.includes('status=stopped'))).toBe(true))
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Search'), { target: { value: 'a2c' } })
    await waitFor(() => expect(call(spy).some((u) => u.includes('q=a2c'))).toBe(true))
    await waitFor(() => expect(screen.queryByText(OLDER.run_id)).not.toBeInTheDocument())
    expect(screen.getByText('ses_0000000e_r1')).toBeInTheDocument()
  })

  it('shows recorded values only and says "Not recorded" for the rest', async () => {
    installHistoryFake({
      runs: [
        makeRun({
          run_id: 'ses_0000000f_r1',
          total_timesteps: null,
          total_episodes: null,
          duration_seconds: null,
          final_metrics: {},
          agent_name: null,
          finished_at: null,
          status: 'interrupted',
          termination_reason: 'unexpected_interruption',
        }),
      ],
    })
    render(
      <MemoryRouter>
        <TrainingHistoryPanel projectId={PROJECT_A} />
      </MemoryRouter>,
    )
    const row = (await screen.findByText('ses_0000000f_r1')).closest('tr') as HTMLElement
    expect(within(row).getAllByText('Not recorded').length).toBeGreaterThanOrEqual(4)
    expect(within(row).getByText('Interrupted (the backend stopped)')).toBeInTheDocument()
  })

  it('distinguishes an empty project from an empty filter result, and reports a load failure', async () => {
    installHistoryFake({ runs: [] })
    const { unmount } = render(
      <MemoryRouter>
        <TrainingHistoryPanel projectId={PROJECT_A} />
      </MemoryRouter>,
    )
    expect(
      await screen.findByText(/No training runs yet\. Train an agent in Studio/),
    ).toBeInTheDocument()
    unmount()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('boom', { status: 500 })),
    )
    render(
      <MemoryRouter>
        <TrainingHistoryPanel projectId={PROJECT_A} />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded')
  })

  it('refreshes only while a run is active, never for finished history', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      const spy = installHistoryFake({ runs: [OLDER] })
      render(
        <MemoryRouter>
          <TrainingHistoryPanel projectId={PROJECT_A} />
        </MemoryRouter>,
      )
      await screen.findByText(OLDER.run_id)
      const before = spy.mock.calls.length
      await act(async () => {
        await vi.advanceTimersByTimeAsync(20_000)
      })
      expect(spy.mock.calls.length).toBe(before)
    } finally {
      vi.useRealTimers()
    }
  })
})
