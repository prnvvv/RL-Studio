import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ServiceQueryState } from '../../hooks/useServiceQuery'
import type { RunLifecycle } from '../../schemas/runs'
import { RunLifecycleStatus } from './RunLifecycleStatus'

const running: RunLifecycle = {
  runId: 'run_1',
  state: 'running',
  rawStatus: 'running',
  failureReported: false,
}

function renderStatus(
  state: ServiceQueryState<RunLifecycle>,
  overrides: Partial<Parameters<typeof RunLifecycleStatus>[0]> = {},
) {
  const onRefresh = vi.fn()
  render(
    <RunLifecycleStatus
      state={state}
      snapshotAsOf="2026-10-25T12:04:09Z"
      onRefresh={onRefresh}
      {...overrides}
    />,
  )
  return { onRefresh }
}

describe('RunLifecycleStatus', () => {
  it('shows a loading state before any status has been read', () => {
    renderStatus({ state: 'loading' })

    expect(screen.getByRole('status', { name: 'Loading data' })).toBeInTheDocument()
  })

  it('renders the backend-reported lifecycle and status read time', () => {
    renderStatus({ state: 'ok', data: running })

    expect(screen.getByText('run_1')).toBeInTheDocument()
    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByText('2026-10-25 12:04:09Z')).toBeInTheDocument()
  })

  it('marks retained data as stale when a status read fails, without changing the state', () => {
    renderStatus({
      state: 'error',
      error: { kind: 'network', message: 'The service could not be reached.' },
      data: running,
    })

    expect(screen.getByRole('status')).toHaveTextContent(/Run status may be out of date/)
    // The last recorded lifecycle is still shown, unchanged.
    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByText(/The service could not be reached\./)).toBeInTheDocument()
    // A lost connection must not be reported as a stopped or failed run.
    expect(screen.queryByText(/stopped/i)).not.toBeInTheDocument()
  })

  it('offers a safe retry, since reading status has no side effects', () => {
    const { onRefresh } = renderStatus({
      state: 'error',
      error: { kind: 'timeout', message: 'The request timed out.' },
      data: null,
    })

    expect(screen.getByRole('alert')).toHaveTextContent('Run status unavailable')
    fireEvent.click(screen.getByRole('button', { name: 'Refresh status' }))

    expect(onRefresh).toHaveBeenCalledTimes(1)
  })
})
