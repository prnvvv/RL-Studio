import { useCallback, useEffect, useState } from 'react'
import type { VoiceDictationState, VoiceTranscriber } from './voiceTranscriber'
import { VoiceStateBadge } from './VoiceStateBadge'

interface VoiceDictationControlProps {
  transcriber: VoiceTranscriber
  /** Receives the final transcript; the parent owns insertion (never auto-submit). */
  onFinalTranscript: (text: string) => void
  /** Receives engine error messages for display next to the control. */
  onErrorMessage?: (message: string) => void
}

const BUTTON_LABELS: Record<'start' | 'stop', string> = {
  start: 'Start dictation',
  stop: 'Stop dictation',
}

/**
 * Browser dictation control on the transcriber boundary.
 *
 * - Buttons always carry text labels; the control is rendered only when the
 *   engine is feature-detected (unsupported browsers get no dead control).
 * - Microphone permission is requested only when the user starts dictation.
 * - The control forwards final transcripts upward and never submits anything
 *   itself — insertion and submission belong to the composer.
 */
export function VoiceDictationControl({ transcriber, onFinalTranscript, onErrorMessage }: VoiceDictationControlProps) {
  const [state, setState] = useState<VoiceDictationState>(transcriber.supported ? 'idle' : 'unsupported')
  const [message, setMessage] = useState<string | undefined>(undefined)

  const handleEvent = useCallback(
    (event: Parameters<Parameters<VoiceTranscriber['subscribe']>[0]>[0]) => {
      if (event.type === 'state') {
        setState(event.state)
        if (event.state !== 'error') setMessage(undefined)
      } else if (event.type === 'transcript') {
        if (event.final) {
          setState('recognised')
          onFinalTranscript(event.text.trim())
        }
      }
    },
    [onFinalTranscript],
  )

  useEffect(() => {
    if (!transcriber.supported) return
    return transcriber.subscribe((event) => {
      if (event.type === 'state' && event.state === 'error') {
        // Error text is surfaced, not silently swallowed.
        setMessage(event.message)
        onErrorMessage?.(event.message)
      }
      handleEvent(event)
    })
  }, [transcriber, handleEvent, onErrorMessage])

  if (!transcriber.supported) {
    return <VoiceStateBadge state="unsupported" />
  }

  const listening = state === 'listening'
  const restartable = state === 'recognised' || state === 'idle' || state === 'error' || state === 'permission_denied'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        {!listening && restartable && (
          <button
            type="button"
            onClick={() => transcriber.start()}
            style={{
              padding: '6px 14px',
              background: 'var(--bg-input)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-primary)',
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
              fontSize: 'var(--text-sm)',
            }}
          >
            {state === 'recognised' ? 'Dictate again' : BUTTON_LABELS.start}
          </button>
        )}
        {listening && (
          <button
            type="button"
            onClick={() => transcriber.stop()}
            style={{
              padding: '6px 14px',
              background: 'var(--bg-panel-raised)',
              border: '1px solid var(--text-primary)',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-primary)',
              cursor: 'pointer',
              fontFamily: 'var(--font-sans)',
              fontSize: 'var(--text-sm)',
              fontWeight: 600,
            }}
          >
            {BUTTON_LABELS.stop}
          </button>
        )}
        <VoiceStateBadge state={state} message={message} />
      </div>
      {state === 'permission_denied' && (
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
          Microphone access was refused by the browser. Type the intent instead, or grant access and dictate again.
        </span>
      )}
    </div>
  )
}
