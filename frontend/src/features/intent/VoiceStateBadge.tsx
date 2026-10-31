import { StatusBadge } from '../../components/ui/StatusBadge'
import type { VoiceDictationState } from './voiceTranscriber'

interface VoiceStateBadgeProps {
  state: VoiceDictationState
  /** Engine-provided, safe message shown under error states. */
  message?: string
}

/** Explicit text label per state — never distinguished by colour alone (§5.2). */
const STATE_LABELS: Record<VoiceDictationState, string> = {
  unsupported: 'Dictation unavailable in this browser',
  permission_denied: 'Microphone permission denied',
  idle: 'Dictation ready',
  listening: 'Listening',
  recognised: 'Speech recognised — review the inserted text',
  error: 'Dictation error',
}

/**
 * Text-labeled badge announcing the dictation state, so every transition is
 * perceivable without relying on motion or colour.
 */
export function VoiceStateBadge({ state, message }: VoiceStateBadgeProps) {
  return (
    <span
      role={state === 'listening' ? 'status' : state === 'error' || state === 'permission_denied' ? 'alert' : undefined}
      style={{ display: 'inline-flex' }}
    >
      <StatusBadge
        label={STATE_LABELS[state]}
        tone={
          state === 'recognised'
            ? 'strong'
            : state === 'unsupported' || state === 'permission_denied' || state === 'idle'
              ? 'quiet'
              : 'neutral'
        }
        glyph={
          state === 'recognised'
            ? 'check'
            : state === 'error' || state === 'permission_denied' || state === 'unsupported'
              ? 'cross'
              : state === 'listening' || state === 'idle'
                ? 'dot'
                : 'query'
        }
        note={state === 'error' && message ? message : undefined}
      />
    </span>
  )
}
