import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { RunLifecycle } from '../../schemas/runs'
import type { RunService } from '../../services/runs'
import type { ServiceResult } from '../../services/types'
import { RunControls } from './RunControls'

function lifecycle(status: RunLifecycle['state'], overrides: Partial<RunLifecycle> = {}) {
  return {
    runId: 'run_1',
    state: status,
    rawStatus: status,
    failureReported: status === 'failed',
    ...overrides,
  } satisfies RunLifecycle
}

function service(overrides: Partial<RunService> = {}): RunService {
  return {
    getRunStatus: vi.fn(async () => ({ state: 'ok', data: lifecycle('running') })),
    startRun: vi.fn(async () => ({ state: 'ok', data: lifecycle('queued') })),
    stopRun: vi.fn(async () => ({
      state: 'ok',
      data: {
        runId: 'run_1',
        state: 'stop_requested',
        rawStatus: 'stop_requested',
        idempotent: true,
      },
    })),
    ...overrides,
  } as RunService
}

function renderControls(
  overrides: Partial<Parameters<typeof RunControls>[0]> = {},
  transport: RunService = service(),
) {
  const onAcknowledged = vi.fn()
  render(
    <RunControls
      runId="run_1"
      lifecycle={lifecycle('running')}
      service={transport}
      onAcknowledged={onAcknowledged}
      {...overrides}
    />,
  )
  return { onAcknowledged, transport }
}

describe('RunControls', () => {
  it('discloses that the endpoints are provisional and do not report training metrics', () => {
    renderControls()

    expect(screen.getByText(/provisional placeholders in the backend/i)).toBeInTheDocument()
    expect(screen.getByText(/not yet connected to the PPO trainer/i)).toBeInTheDocument()
  })

  it('blocks starting while a task is already recorded, and says why', () => {
    renderControls()

    expect(screen.getByRole('button', { name: 'Start training' })).toBeDisabled()
    expect(
      screen.getByText(/Start unavailable: A training task is already recorded/i),
    ).toBeInTheDocument()
  })

  it('blocks both actions when the lifecycle has not been read', () => {
    renderControls({ lifecycle: null })

    expect(screen.getByRole('button', { name: 'Start training' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Stop run' })).toBeDisabled()
    expect(screen.getByText(/has not been read, so starting is blocked/i)).toBeInTheDocument()
    expect(screen.getByText(/has not been read, so stopping is blocked/i)).toBeInTheDocument()
  })

  it('fails closed for an unrecognised backend status', () => {
    renderControls({
      lifecycle: lifecycle('unrecognized', { rawStatus: 'paused' }),
    })

    expect(screen.getByRole('button', { name: 'Start training' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Stop run' })).toBeDisabled()
    // Both actions state the same reason, so both explanations must be present.
    expect(screen.getAllByText(/The reported status is not recognised/i)).toHaveLength(2)
  })

  it('reports a start acknowledgement as accepted status, not as training started', async () => {
    const { onAcknowledged } = renderControls({
      lifecycle: lifecycle('unknown', { rawStatus: 'unknown' }),
    })

    fireEvent.click(screen.getByRole('button', { name: 'Start training' }))

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        'The backend accepted the start request for run run_1 and reported status "queued".',
      ),
    )
    expect(screen.queryByText(/training started/i)).not.toBeInTheDocument()
    expect(onAcknowledged).toHaveBeenCalledWith({
      kind: 'started',
      acknowledgement: expect.objectContaining({ state: 'queued' }),
    })
  })

  it('prevents duplicate start submissions while a request is in flight', async () => {
    let resolveStart: (result: ServiceResult<RunLifecycle>) => void = () => {}
    const startRun = vi.fn(
      () =>
        new Promise<ServiceResult<RunLifecycle>>((resolve) => {
          resolveStart = resolve
        }),
    )
    const transport = service({ startRun })

    const { onAcknowledged } = renderControls(
      { lifecycle: lifecycle('unknown', { rawStatus: 'unknown' }) },
      transport,
    )

    const start = screen.getByRole('button', { name: 'Start training' })
    fireEvent.click(start)
    fireEvent.click(start)

    expect(startRun).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Starting…' })).toBeDisabled()

    resolveStart({ state: 'ok', data: lifecycle('queued') })

    // The in-flight label is cleared once the request settles, and the page is
    // told to re-read the lifecycle; the control never adopts the response as
    // its own status.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Start training' })).not.toHaveAttribute(
        'aria-busy',
      ),
    )
    expect(onAcknowledged).toHaveBeenCalledWith({
      kind: 'started',
      acknowledgement: expect.objectContaining({ runId: 'run_1', state: 'queued' }),
    })
  })

  it('leaves a timed-out start explicitly unknown and never retries', async () => {
    const startRun = vi.fn(async () => ({
      state: 'error',
      error: { kind: 'timeout', message: 'The request timed out.' },
    })) as unknown as RunService['startRun']
    const transport = service({ startRun })

    renderControls({ lifecycle: lifecycle('unknown', { rawStatus: 'unknown' }) }, transport)

    fireEvent.click(screen.getByRole('button', { name: 'Start training' }))

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        /may or may not have queued a task for this run/i,
      ),
    )
    expect(startRun).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('status')).toHaveTextContent(/does not retry automatically/i)
  })

  it('requires confirmation before requesting a stop', async () => {
    const { transport, onAcknowledged } = renderControls()

    fireEvent.click(screen.getByRole('button', { name: 'Stop run' }))

    expect(transport.stopRun).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Request stop' }))

    await waitFor(() => expect(transport.stopRun).toHaveBeenCalledWith('run_1'))
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        'Stop requested for run run_1. The run is not stopped until the backend reports a stopped state.',
      ),
    )
    expect(screen.queryByText(/^The run is stopped\.$/)).not.toBeInTheDocument()
    expect(onAcknowledged).toHaveBeenCalledWith({
      kind: 'stop_requested',
      acknowledgement: expect.objectContaining({ state: 'stop_requested' }),
    })
  })

  it('cancels a stop request without contacting the backend', () => {
    const { transport } = renderControls()

    fireEvent.click(screen.getByRole('button', { name: 'Stop run' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(transport.stopRun).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('blocks a repeated stop once one has been requested', () => {
    renderControls({ lifecycle: lifecycle('stop_requested') })

    expect(screen.getByRole('button', { name: 'Stop run' })).toBeDisabled()
    expect(
      screen.getByText(/Stop unavailable: A stop has already been requested/i),
    ).toBeInTheDocument()
  })

  it('surfaces a conflict from the backend verbatim instead of retrying', async () => {
    const stopRun = vi.fn(async () => ({
      state: 'error',
      error: { kind: 'conflict', message: 'The recorded state does not allow this request.' },
    })) as unknown as RunService['stopRun']
    const transport = service({ stopRun })

    renderControls({}, transport)

    fireEvent.click(screen.getByRole('button', { name: 'Stop run' }))
    fireEvent.click(screen.getByRole('button', { name: 'Request stop' }))

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'The recorded state does not allow this request.',
      ),
    )
    expect(stopRun).toHaveBeenCalledTimes(1)
  })
})
