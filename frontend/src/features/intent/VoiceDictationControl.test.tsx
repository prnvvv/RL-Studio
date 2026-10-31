import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { createWebSpeechTranscriber, type TranscriberEvent, type VoiceTranscriber } from './voiceTranscriber'
import { VoiceDictationControl } from './VoiceDictationControl'

/** Scripted double of the boundary so tests control every state transition. */
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

describe('VoiceDictationControl', () => {
  it('renders only an honest unsupported badge when no engine exists', () => {
    render(<VoiceDictationControl transcriber={createWebSpeechTranscriber(null)} onFinalTranscript={() => undefined} />)
    expect(screen.getByText('Dictation unavailable in this browser')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('starts dictation from the explicit button and offers stop while listening', () => {
    const { transcriber, emit } = scriptedTranscriber()
    render(<VoiceDictationControl transcriber={transcriber} onFinalTranscript={() => undefined} />)

    fireEvent.click(screen.getByRole('button', { name: 'Start dictation' }))
    expect(screen.getByRole('button', { name: 'Stop dictation' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Listening')

    act(() => emit({ type: 'state', state: 'idle', message: undefined }))
    expect(screen.getByRole('button', { name: 'Start dictation' })).toBeInTheDocument()
  })

  it('forwards final transcripts and never submits them itself', () => {
    const { transcriber, emit } = scriptedTranscriber()
    const onFinalTranscript = vi.fn()
    render(<VoiceDictationControl transcriber={transcriber} onFinalTranscript={onFinalTranscript} />)

    act(() => emit({ type: 'transcript', text: '  goal reward must equal 100.  ', final: true }))
    expect(onFinalTranscript).toHaveBeenCalledOnce()
    expect(onFinalTranscript).toHaveBeenCalledWith('goal reward must equal 100.')
    // A recognised transcript adjusts the control state but does not invoke
    // any submit path — there is none in this component.
    expect(screen.getByText('Speech recognised — review the inserted text')).toBeInTheDocument()
  })

  it('ignores interim transcripts until finalisation', () => {
    const { transcriber, emit } = scriptedTranscriber()
    const onFinalTranscript = vi.fn()
    render(<VoiceDictationControl transcriber={transcriber} onFinalTranscript={onFinalTranscript} />)

    act(() => emit({ type: 'transcript', text: 'goal rew', final: false }))
    expect(onFinalTranscript).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Start dictation' })).toBeInTheDocument()
  })

  it('shows engine problems via onErrorMessage and a labelled alert', () => {
    const { transcriber, emit } = scriptedTranscriber()
    const onErrorMessage = vi.fn()
    render(<VoiceDictationControl transcriber={transcriber} onFinalTranscript={() => undefined} onErrorMessage={onErrorMessage} />)

    act(() => emit({ type: 'state', state: 'error', message: 'No speech was detected.' }))
    expect(onErrorMessage).toHaveBeenCalledTimes(1)
    expect(onErrorMessage).toHaveBeenCalledWith('No speech was detected.')
    expect(screen.getByText('No speech was detected.')).toBeInTheDocument()

    act(() => emit({ type: 'state', state: 'permission_denied', message: undefined }))
    expect(screen.getByText('Microphone permission denied')).toBeInTheDocument()
  })

  it('labels restart after a recognised session', () => {
    const { transcriber, emit } = scriptedTranscriber()
    render(<VoiceDictationControl transcriber={transcriber} onFinalTranscript={() => undefined} />)

    act(() => emit({ type: 'transcript', text: 'restart check', final: true }))
    expect(screen.getByRole('button', { name: 'Dictate again' })).toBeInTheDocument()
  })
})
