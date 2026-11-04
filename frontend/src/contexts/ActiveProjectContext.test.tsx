import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ActiveProjectChip } from '../features/projects/ActiveProjectChip'
import { PID, failure, fakeService, project } from '../features/projects/projectFixtures'
import { ActiveProjectProvider, useActiveProject } from './ActiveProjectContext'

const KEY = 'rl-studio.activeProject'

function Show() {
  const { activeProjectId, setActiveProjectId } = useActiveProject()
  return (
    <>
      <span data-testid="id">{activeProjectId ?? 'none'}</span>
      <button onClick={() => setActiveProjectId(PID)}>set</button>
      <button onClick={() => setActiveProjectId(null)}>clear</button>
    </>
  )
}

beforeEach(() => window.localStorage.clear())
afterEach(() => vi.unstubAllGlobals())

describe('ActiveProjectContext', () => {
  it('is safe without a provider', () => {
    render(<Show />)
    expect(screen.getByTestId('id')).toHaveTextContent('none')
  })

  it('survives a refresh through storage and ignores malformed stored values', () => {
    window.localStorage.setItem(KEY, PID)
    const first = render(
      <ActiveProjectProvider>
        <Show />
      </ActiveProjectProvider>,
    )
    expect(screen.getByTestId('id')).toHaveTextContent(PID)
    first.unmount()

    window.localStorage.setItem(KEY, '../../etc/passwd')
    render(
      <ActiveProjectProvider>
        <Show />
      </ActiveProjectProvider>,
    )
    expect(screen.getByTestId('id')).toHaveTextContent('none')
  })

  it('persists a selection and clears it', () => {
    render(
      <ActiveProjectProvider>
        <Show />
      </ActiveProjectProvider>,
    )
    act(() => screen.getByText('set').click())
    expect(window.localStorage.getItem(KEY)).toBe(PID)
    act(() => screen.getByText('clear').click())
    expect(window.localStorage.getItem(KEY)).toBeNull()
  })

  it('still works in memory when storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    render(
      <ActiveProjectProvider>
        <Show />
      </ActiveProjectProvider>,
    )
    act(() => screen.getByText('set').click())
    expect(screen.getByTestId('id')).toHaveTextContent(PID)
    vi.restoreAllMocks()
  })
})

describe('ActiveProjectChip', () => {
  function renderChip(service = fakeService()) {
    return render(
      <ActiveProjectProvider>
        <MemoryRouter>
          <ActiveProjectChip service={service} />
          <Show />
        </MemoryRouter>
      </ActiveProjectProvider>,
    )
  }

  it('renders nothing without an active project', () => {
    renderChip()
    expect(screen.queryByRole('link', { name: /Active project/ })).not.toBeInTheDocument()
  })

  it('names the active project and links to its workspace', async () => {
    window.localStorage.setItem(KEY, PID)
    renderChip(
      fakeService({
        getProject: vi.fn(async () => ({ state: 'ok' as const, data: project({ name: 'Alpha' }) })),
      }),
    )
    const link = await screen.findByRole('link', { name: 'Active project: Alpha' })
    expect(link).toHaveAttribute('href', `/projects/${PID}`)
  })

  it('drops a project that no longer exists instead of showing it as active', async () => {
    window.localStorage.setItem(KEY, PID)
    renderChip(fakeService({ getProject: vi.fn(() => failure('not_found', 404)) as never }))
    await waitFor(() => expect(screen.getByTestId('id')).toHaveTextContent('none'))
    expect(window.localStorage.getItem(KEY)).toBeNull()
  })

  it('keeps the pointer when the backend is unreachable', async () => {
    window.localStorage.setItem(KEY, PID)
    renderChip(fakeService({ getProject: vi.fn(() => failure('network')) as never }))
    expect(await screen.findByRole('link', { name: `Active project: ${PID}` })).toBeInTheDocument()
    expect(screen.getByTestId('id')).toHaveTextContent(PID)
  })
})
