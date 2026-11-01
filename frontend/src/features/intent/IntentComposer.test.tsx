import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ExtractedRequirementDraft, IntentSubmissionResult, RequirementDecision } from '../../schemas/intent'
import { MOCK_DATA_LABEL, type MockData } from '../../mocks'
import type { IntentSubmissionOutcome } from '../../services/intentRequirements'
import type { TranscriberEvent, VoiceTranscriber } from './voiceTranscriber'
import { IntentComposer } from './IntentComposer'

const acceptedPayload: IntentSubmissionResult = {
  schema_version: '1.0',
  extraction_status: 'accepted',
  warnings: [],
  requirements: [
    {
      requirement_id: 'req_mock_goal_reward',
      description: 'Goal reward must equal the confirmed value.',
      rule_type: 'expected_reward',
      parameters: { expected: 100 },
      tolerance: null,
      source: 'developer_confirmed',
      confirmed: null,
      environment_version: 'warehouse_v1',
    },
  ],
  timestamp: null,
}

/** Scripted transcriber double for insertion-flow control. */
function scriptedTranscriber() {
  const listeners = new Set<(event: TranscriberEvent) => void>()
  const emit = (event: TranscriberEvent) => {
    for (const listener of listeners) listener(event)
  }
  const transcriber: VoiceTranscriber = {
    supported: true,
    start: () => emit({ type: 'state', state: 'listening', message: undefined }),
    stop: () => emit({ type: 'state', state: 'idle', message: undefined }),
    subscribe: (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
  }
  return { transcriber, emit }
}

describe('IntentComposer — text submission', () => {
  it('submits edited text explicitly and shows the waiting state', async () => {
    const onSubmit = vi.fn(async () => ({ state: 'ok', data: acceptedPayload }) as IntentSubmissionOutcome)
    render(<IntentComposer onSubmit={onSubmit} onDecide={async () => undefined} />)

    const area = screen.getByLabelText('Intended behaviour') as HTMLTextAreaElement
    fireEvent.change(area, { target: { value: 'The goal reward must be 100.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit intent' }))

    expect(screen.getByRole('status')).toHaveTextContent('Submitting intent')
    expect(screen.getByRole('button', { name: 'Submit intent' })).toBeDisabled()
    // Text stays editable and preserved while the request is in flight.
    expect((screen.getByLabelText('Intended behaviour') as HTMLTextAreaElement).value).toBe(
      'The goal reward must be 100.',
    )

    await waitFor(() => expect(screen.getByText('Goal reward must equal the confirmed value.')).toBeInTheDocument())
    expect(onSubmit).toHaveBeenCalledWith('The goal reward must be 100.')
  })

  it('disables submission until text is entered', async () => {
    render(<IntentComposer onSubmit={async () => ({ state: 'ok', data: acceptedPayload })} onDecide={async () => undefined} />)
    expect(screen.getByRole('button', { name: 'Submit intent' })).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Intended behaviour'), { target: { value: '   ' } })
    expect(screen.getByRole('button', { name: 'Submit intent' })).toBeDisabled()
  })

  it('renders accepted drafts through the review list', async () => {
    render(<IntentComposer onSubmit={async () => ({ state: 'ok', data: acceptedPayload })} onDecide={async () => undefined} />)
    fireEvent.change(screen.getByLabelText('Intended behaviour'), { target: { value: 'The goal reward must be 100.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit intent' }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Requirements extracted'))
    expect(screen.getAllByRole('button', { name: 'Confirm' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Reject' })).toHaveLength(1)
  })

  it('reports ambiguous and unsupported statements with warnings, without drafts', async () => {
    for (const extraction_status of ['ambiguous', 'unsupported'] as const) {
      const { unmount } = render(
        <IntentComposer
          onSubmit={
            async () =>
              ({
                state: 'ok',
                data: { ...acceptedPayload, extraction_status, warnings: ['No exact expected value could be parsed.'] },
              }) as IntentSubmissionOutcome
          }
          onDecide={async () => undefined}
        />,
      )
      fireEvent.change(screen.getByLabelText('Intended behaviour'), { target: { value: 'Some intent statement.' } })
      fireEvent.click(screen.getByRole('button', { name: 'Submit intent' }))
      await waitFor(() => expect(screen.getByText('No exact expected value could be parsed.')).toBeInTheDocument())
      expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument()
      unmount()
    }
  })

  it('shows an honest error state with a safe retry for failed submissions', async () => {
    const onSubmit = vi
      .fn<() => Promise<IntentSubmissionOutcome>>()
      .mockResolvedValueOnce({ state: 'error', error: { kind: 'not_found', message: 'The requested record was not found.' } })
      .mockResolvedValueOnce({ state: 'ok', data: acceptedPayload })
    render(<IntentComposer onSubmit={onSubmit} onDecide={async () => undefined} />)

    fireEvent.change(screen.getByLabelText('Intended behaviour'), { target: { value: 'The goal reward must be 100.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit intent' }))
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText('The intent could not be submitted')).toBeInTheDocument()
    // The statement is preserved for the retry.
    expect((screen.getByLabelText('Intended behaviour', {}) as HTMLTextAreaElement).value).toBe(
      'The goal reward must be 100.',
    )

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(screen.getByText('Goal reward must equal the confirmed value.')).toBeInTheDocument())
    expect(onSubmit).toHaveBeenCalledTimes(2)
  })

  it('labels mock-fed results as sample data', async () => {
    const wrapped: MockData<IntentSubmissionResult> = { data: acceptedPayload, label: MOCK_DATA_LABEL }
    render(<IntentComposer onSubmit={async () => ({ state: 'ok', data: wrapped })} onDecide={async () => undefined} />)
    fireEvent.change(screen.getByLabelText('Intended behaviour'), { target: { value: 'The goal reward must be 100.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit intent' }))
    await waitFor(() => expect(screen.getByText(MOCK_DATA_LABEL)).toBeInTheDocument())
  })
})

describe('IntentComposer — voice insertion', () => {
  it('inserts the transcript at the cursor and never submits automatically', async () => {
    const { transcriber, emit } = scriptedTranscriber()
    const onSubmit = vi.fn(async () => ({ state: 'ok', data: acceptedPayload }) as IntentSubmissionOutcome)
    render(<IntentComposer onSubmit={onSubmit} onDecide={async () => undefined} transcriber={transcriber} />)

    const area = screen.getByLabelText('Intended behaviour') as HTMLTextAreaElement
    // Pre-existing text the user typed themselves.
    fireEvent.change(area, { target: { value: 'The goal reward must be 100.' } })
    area.setSelectionRange(area.value.length, area.value.length)

    act(() => emit({ type: 'transcript', text: 'Step penalty must equal 1.', final: true }))

    // Inserted text is editable content; the submit action was NOT invoked.
    expect(onSubmit).not.toHaveBeenCalled()
    const after = screen.getByLabelText('Intended behaviour') as HTMLTextAreaElement
    expect(after.value).toBe('The goal reward must be 100. Step penalty must equal 1.')

    fireEvent.click(screen.getByRole('button', { name: 'Submit intent' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce())
  })

  it('joins inserted text with a space and never overwrites existing content', () => {
    const { transcriber, emit } = scriptedTranscriber()
    const onSubmit = vi.fn(async () => ({ state: 'ok', data: acceptedPayload }) as IntentSubmissionOutcome)
    render(<IntentComposer onSubmit={onSubmit} onDecide={async () => undefined} transcriber={transcriber} />)

    const area = screen.getByLabelText('Intended behaviour') as HTMLTextAreaElement
    fireEvent.change(area, { target: { value: 'Observations stay intact' } })
    area.setSelectionRange(area.value.length, area.value.length)

    act(() => emit({ type: 'transcript', text: 'Termination must be recorded.', final: true }))
    expect((screen.getByLabelText('Intended behaviour') as HTMLTextAreaElement).value).toBe(
      'Observations stay intact Termination must be recorded.',
    )
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Submit intent' })).toBeEnabled()
  })
})

describe('IntentComposer — review decisions', () => {
  it('records the confirm decision per draft and shows pending isolation', async () => {
    const onDecide = vi.fn<(draft: ExtractedRequirementDraft, decision: RequirementDecision) => Promise<void>>(
      async () => undefined,
    )
    render(<IntentComposer onSubmit={async () => ({ state: 'ok', data: acceptedPayload })} onDecide={onDecide} />)

    fireEvent.change(screen.getByLabelText('Intended behaviour'), { target: { value: 'The goal reward must be 100.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit intent' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled())

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await waitFor(() => expect(screen.getByText('Confirmed for this session')).toBeInTheDocument())
    expect(onDecide).toHaveBeenCalledOnce()
    expect(onDecide.mock.calls.length).toBeGreaterThan(0)
    const [draftArg, decisionArg] = onDecide.mock.calls[0]!
    expect(draftArg).toMatchObject({ requirement_id: 'req_mock_goal_reward' })
    expect(decisionArg).toBe('confirm')
  })

  it('surfaces failed decision recording without discarding drafts', async () => {
    const onDecide = vi.fn(async () => {
      throw new Error('boom')
    })
    render(<IntentComposer onSubmit={async () => ({ state: 'ok', data: acceptedPayload })} onDecide={onDecide} />)

    fireEvent.change(screen.getByLabelText('Intended behaviour'), { target: { value: 'The goal reward must be 100.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Submit intent' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    await waitFor(() => expect(screen.getByText(/decision could not be recorded/)).toBeInTheDocument())
    // The draft list is kept intact for a retry.
    expect(screen.getByText('Goal reward must equal the confirmed value.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeEnabled()
  })
})
